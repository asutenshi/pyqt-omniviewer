import importlib.util
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from omniviewer.viewers.base import BaseViewer

try:
    import mpv
    MPV_AVAILABLE = True
except (ImportError, OSError):
    MPV_AVAILABLE = False

MUTAGEN_AVAILABLE = importlib.util.find_spec("mutagen") is not None


## @brief Единственный на процесс QMediaPlayer и его виджеты.
#
# Уничтожить живой QMediaPlayer из GUI-потока нельзя: бэкенд Qt FFmpeg на destroy
# делает join своих рабочих потоков прямо в GUI-потоке и намертво вешает
# приложение (зависший процесс затем добивается SIGKILL'ом — «Killed» в логе).
# То же касается снятия источника (`setSource(QUrl())`) и уничтожения привязанного
# QVideoWidget во время активного конвейера. Поэтому плеер, его звуковой выход и
# видеовиджет создаются один раз и живут всё время работы программы; просмотрщики
# лишь переключают источник (это безопасно) и перецепляют общий видеовиджет в свой
# layout. Одновременно активен максимум один MediaViewer, так что общий набор
# ресурсов достаточен.
class _SharedPlayer:
    _player: QMediaPlayer | None = None
    _audio: QAudioOutput | None = None
    _video: QVideoWidget | None = None
    # Постоянный «домик» для общего видеовиджета: пока просмотрщик не показывает
    # видео, виджет припаркован здесь, а не висит в дереве уничтожаемого
    # MediaViewer (иначе Qt снесёт его вместе с родителем).
    _keeper: QWidget | None = None

    @classmethod
    def _alive(cls) -> bool:
        try:
            if cls._player is None:
                return False
            cls._player.playbackState()  # обращение к C++: бросит, если объект снесён
            cls._video.isVisible()
        except RuntimeError:
            return False
        return True

    @classmethod
    def acquire(cls) -> tuple[QMediaPlayer, QAudioOutput, QVideoWidget]:
        if not cls._alive():
            cls._keeper = QWidget()
            cls._keeper.setLayout(QVBoxLayout())
            cls._player = QMediaPlayer()
            cls._audio = QAudioOutput()
            cls._video = QVideoWidget(cls._keeper)
            cls._player.setAudioOutput(cls._audio)
            cls._player.setVideoOutput(cls._video)
        return cls._player, cls._audio, cls._video

    @classmethod
    def release(cls) -> None:
        """Остановить воспроизведение и припарковать общий видеовиджет.

        Сам плеер не уничтожается никогда (см. описание класса). ``stop()`` —
        синхронно безопасен, в отличие от destroy/``setSource(QUrl())``.
        """
        if not cls._alive():
            return
        cls._player.stop()
        cls._video.setParent(cls._keeper)
        cls._video.hide()


## @brief Просмотрщик медиафайлов (видео и аудио).
#
# Использует общий QMediaPlayer (:class:`_SharedPlayer`) для воспроизведения.
# При ошибках штатного движка пытается использовать запасной (libmpv).
# Для аудио извлекает метаданные (теги и обложку) через mutagen.
class MediaViewer(BaseViewer):
    mime_types = (
        "video/mp4",
        "video/x-matroska",
        "video/x-msvideo",
        "video/webm",
        "video/quicktime",
        "audio/mpeg",
        "audio/flac",
        "audio/vnd.wave",
        "audio/x-wav",
        "audio/ogg",
        "audio/mp4",
        "audio/x-m4a",
        "audio/opus",
    )
    extensions = (
        ".mp4", ".mkv", ".avi", ".webm", ".mov",
        ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".opus",
    )
    priority = 10

    # Сигналы общего плеера, которые каждый просмотрщик подключает на время
    # своей жизни и обязан отключить в cancel().
    _SIGNAL_SLOTS = (
        ("errorOccurred", "on_qt_error"),
        ("positionChanged", "update_position"),
        ("durationChanged", "update_duration"),
        ("playbackStateChanged", "update_state"),
        ("mediaStatusChanged", "on_media_status"),
    )

    def __init__(self):
        super().__init__()
        self.player: QMediaPlayer | None = None
        self.audio_output: QAudioOutput | None = None
        self.mpv_player = None
        self._path = None
        self._connected = False

        # Общий видеовиджет перецепляется сюда на время показа.
        self.video_widget = QWidget(self)
        self._video_layout = QVBoxLayout(self.video_widget)
        self._video_layout.setContentsMargins(0, 0, 0, 0)

        self.cover_label = QLabel(self)
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.hide()

        self.tags_label = QLabel(self)
        self.tags_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tags_label.hide()
        self.tags_label.setWordWrap(True)

        # Controls
        self.controls_layout = QHBoxLayout()
        self.play_btn = QPushButton("Play")
        self.play_btn.clicked.connect(self.toggle_play)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.sliderMoved.connect(self.set_position)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(100)
        self.volume_slider.valueChanged.connect(self.set_volume)

        self.controls_layout.addWidget(self.play_btn)
        self.controls_layout.addWidget(self.seek_slider)
        self.controls_layout.addWidget(QLabel("Vol:"))
        self.controls_layout.addWidget(self.volume_slider)

        self._layout.addWidget(self.video_widget, 1)
        self._layout.addWidget(self.cover_label, 1)
        self._layout.addWidget(self.tags_label)
        self._layout.addLayout(self.controls_layout)

    def load(self, path: Path):
        self._path = path
        if path.stat().st_size < 100:
            raise ValueError("File is too small to be valid media")

        # Audio tags
        if MUTAGEN_AVAILABLE:
            try:
                from mutagen import File
                audio = File(str(path))
                if audio is not None:
                    tags = []
                    # Try to extract basic tags
                    for key in ["artist", "title", "album", "ARTIST", "TITLE", "ALBUM"]:
                        if key in audio:
                            val = audio[key]
                            if isinstance(val, list):
                                val = val[0]
                            tags.append(f"{key.capitalize()}: {val}")
                    if tags:
                        self.tags_label.setText(" | ".join(tags))
                        self.tags_label.show()

                    # Extract cover
                    cover_data = None
                    if hasattr(audio, "tags") and audio.tags:
                        for tag in audio.tags.values():
                            if hasattr(tag, "data") and hasattr(tag, "type") and tag.type == 3 or hasattr(tag, "data") and type(tag).__name__ == "Picture":
                                cover_data = tag.data
                                break
                    if cover_data:
                        pixmap = QPixmap()
                        pixmap.loadFromData(cover_data)
                        if not pixmap.isNull():
                            self.cover_label.setPixmap(pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                            self.cover_label.show()
            except Exception:  # noqa: BLE001, S110 - теги необязательны, разбор best-effort
                pass

        # QMediaPlayer — поднимаем после возврата в цикл событий
        QTimer.singleShot(0, self._init_player)

    def _init_player(self):
        if self._path is None:  # load() уже отменён — плеер поднимать не нужно
            return
        self.player, self.audio_output, shared_video = _SharedPlayer.acquire()

        # Перецепляем общий видеовиджет в наш layout.
        shared_video.setParent(self.video_widget)
        self._video_layout.addWidget(shared_video)
        shared_video.show()

        for signal_name, slot_name in self._SIGNAL_SLOTS:
            getattr(self.player, signal_name).connect(getattr(self, slot_name))
        self._connected = True

        self.audio_output.setVolume(self.volume_slider.value() / 100.0)
        self.player.setSource(QUrl.fromLocalFile(str(self._path)))
        self.player.pause()

    def _disconnect_player(self):
        if self.player is not None and self._connected:
            for signal_name, slot_name in self._SIGNAL_SLOTS:
                try:
                    getattr(self.player, signal_name).disconnect(getattr(self, slot_name))
                except (TypeError, RuntimeError):
                    pass
        self._connected = False

    def on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.InvalidMedia:
            if MPV_AVAILABLE:
                self.fallback_to_mpv()
            else:
                self._show_error(Exception("Invalid media file (QMediaPlayer failed)"), "")

    def on_qt_error(self, error, error_string=""):
        if error != QMediaPlayer.Error.NoError:
            if MPV_AVAILABLE:
                self.fallback_to_mpv()
            else:
                self._show_error(Exception(f"QMediaPlayer error: {self.player.errorString()}"), traceback.format_exc())

    def fallback_to_mpv(self):
        if self.mpv_player is not None:  # уже переключились — второй сигнал ошибки игнорируем
            return
        try:
            self._disconnect_player()
            if self.player is not None:
                self.player.stop()

            _, _, shared_video = _SharedPlayer.acquire()
            self.mpv_player = mpv.MPV(wid=str(int(shared_video.winId())))
            self.mpv_player.play(str(self._path))
            # Just minimal fallback
        except Exception as e:  # noqa: BLE001 - запасной движок не должен ронять UI
            self._show_error(e, traceback.format_exc())

    def toggle_play(self):
        if self.player:
            if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
            else:
                self.player.play()
        elif self.mpv_player:
            self.mpv_player.pause = not getattr(self.mpv_player, 'pause', False)

    def update_position(self, position):
        if not self.seek_slider.isSliderDown():
            self.seek_slider.setValue(position)

    def update_duration(self, duration):
        self.seek_slider.setRange(0, duration)

    def set_position(self, position):
        if self.player:
            self.player.setPosition(position)
        elif self.mpv_player:
            try:
                self.mpv_player.time_pos = position / 1000.0
            except Exception:  # noqa: BLE001, S110 - перемотка best-effort, mpv не должен ронять UI
                pass

    def set_volume(self, volume):
        if self.audio_output:
            self.audio_output.setVolume(volume / 100.0)
        elif self.mpv_player:
            try:
                self.mpv_player.volume = volume
            except Exception:  # noqa: BLE001, S110 - громкость best-effort, mpv не должен ронять UI
                pass

    def update_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("Pause")
        else:
            self.play_btn.setText("Play")

    def __del__(self):
        # Страховка на случай уничтожения без cancel() (например, в смоук-тестах):
        # общий видеовиджет надо выцепить из уничтожаемого дерева MediaViewer до
        # того, как C++-деструктор дойдёт до ~QVideoWidget при живом конвейере —
        # иначе GUI-поток зависнет на join рабочих потоков FFmpeg-бэкенда Qt.
        try:
            _SharedPlayer.release()
        except Exception:  # noqa: BLE001, S110
            pass

    def cancel(self):
        super().cancel()
        self._path = None
        if self.mpv_player is not None:
            try:
                self.mpv_player.terminate()
            except Exception:  # noqa: BLE001, S110
                pass
            self.mpv_player = None
        self._disconnect_player()
        _SharedPlayer.release()
        self.player = None
        self.audio_output = None
