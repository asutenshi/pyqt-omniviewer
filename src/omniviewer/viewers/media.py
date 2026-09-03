_DELAYED_GC_PLAYERS = []
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QPixmap
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
)

from omniviewer.viewers.base import BaseViewer

try:
    import mpv
    MPV_AVAILABLE = True
except (ImportError, OSError):
    MPV_AVAILABLE = False

try:
    import mutagen
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False


## @brief Просмотрщик медиафайлов (видео и аудио).
#
# Использует QMediaPlayer для воспроизведения.
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

    def __init__(self):
        super().__init__()
        self.player = None
        self.mpv_player = None
        self.audio_output = None
        self._path = None
        
        self.video_widget = QVideoWidget(self)
        
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
            raise Exception("File is too small to be valid media")
        
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
                        for tag_name, tag in audio.tags.items():
                            if hasattr(tag, "data") and hasattr(tag, "type") and tag.type == 3 or hasattr(tag, "data") and type(tag).__name__ == "Picture":
                                cover_data = tag.data
                                break
                    if cover_data:
                        pixmap = QPixmap()
                        pixmap.loadFromData(cover_data)
                        if not pixmap.isNull():
                            self.cover_label.setPixmap(pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                            self.cover_label.show()
            except Exception:
                pass

        # QMediaPlayer
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._init_player)

    def _init_player(self):
        self.player = QMediaPlayer()
        _DELAYED_GC_PLAYERS.append(self.player)
        if len(_DELAYED_GC_PLAYERS) > 2:
            old_player = _DELAYED_GC_PLAYERS.pop(0)
            old_player.deleteLater()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.player.errorOccurred.connect(self.on_qt_error)
        self.player.positionChanged.connect(self.update_position)
        self.player.durationChanged.connect(self.update_duration)
        self.player.playbackStateChanged.connect(self.update_state)
        self.player.mediaStatusChanged.connect(self.on_media_status)
        self.player.setSource(QUrl.fromLocalFile(str(self._path)))
        self.player.pause()
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
        try:
            self.player.stop()
            self.player.deleteLater()
            self.player = None
            
            self.mpv_player = mpv.MPV(wid=str(int(self.video_widget.winId())))
            self.mpv_player.play(str(self._path))
            # Just minimal fallback
        except Exception as e:
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
            except Exception:
                pass

    def set_volume(self, volume):
        if self.audio_output:
            self.audio_output.setVolume(volume / 100.0)
        elif self.mpv_player:
            try:
                self.mpv_player.volume = volume
            except Exception:
                pass

    def update_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.play_btn.setText("Pause")
        else:
            self.play_btn.setText("Play")

    def cancel(self):
        super().cancel()
        if self.player:
            self.player.stop()
        if self.mpv_player:
            try:
                self.mpv_player.terminate()
            except Exception:
                pass
