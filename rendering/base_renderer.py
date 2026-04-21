# ===== Rendering - בסיס =====
# ממשק אחיד: כל renderer מקבל TypeA או TypeB ומפיק קובץ פלט.

from abc import ABC, abstractmethod


class BaseRenderer(ABC):

    @abstractmethod
    def render(self, report, output_path: str) -> str:
        """
        מקבל דוח (TypeA / TypeB) ונתיב פלט.
        מפיק את הקובץ ומחזיר את הנתיב שנוצר.
        """
        pass
