from dataclasses import dataclass


@dataclass
class DiskwalaError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"
