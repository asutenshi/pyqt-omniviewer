
from .mime import detect_mime
from .viewers.base import BaseViewer


class ViewerRegistry:
    """Реестр обработчиков для просмотра файлов."""
    
    def __init__(self):
        self._viewers: list[type[BaseViewer]] = []
        self._fallback_viewer: type[BaseViewer] | None = None
        
    def register(self, viewer_cls: type[BaseViewer]):
        """Регистрирует класс просмотрщика."""
        if not hasattr(viewer_cls, "can_handle"):
            return
        
        self._viewers.append(viewer_cls)
        # Сортируем по убыванию приоритета (высший приоритет первым)
        self._viewers.sort(key=lambda cls: getattr(cls, "priority", 0), reverse=True)
        
    def set_fallback(self, viewer_cls: type[BaseViewer]):
        """Устанавливает резервный просмотрщик (низший приоритет)."""
        self._fallback_viewer = viewer_cls
        
    def viewer_for(self, path: str) -> BaseViewer:
        """
        Возвращает экземпляр подходящего просмотрщика для файла.
        """
        mime = detect_mime(path)
        for viewer_cls in self._viewers:
            if viewer_cls.can_handle(path, mime):
                return viewer_cls()
                
        if self._fallback_viewer:
            return self._fallback_viewer()
            
        return BaseViewer() # В идеале сюда не доходим, если есть fallback
        
# Глобальный экземпляр реестра
registry = ViewerRegistry()
