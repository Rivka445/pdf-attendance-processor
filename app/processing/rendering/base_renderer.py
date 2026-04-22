from abc import ABC, abstractmethod


class BaseRenderer(ABC):

    @abstractmethod
    def render(self, report, output_path: str) -> str:
        """Render a report object to a file and return the output path."""
        pass
