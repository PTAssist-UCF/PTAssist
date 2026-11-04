"""Stand-ins shared by the keypoint tests, so they need no real ffmpeg process."""

import io


class FakePipe(io.BytesIO):
    """ffmpeg's stdin; keeps what was written after it is closed, in `data`.

    With `close_error`, closing raises it, as a pipe to an exited ffmpeg does.
    """

    def __init__(self, close_error: OSError | None = None) -> None:
        super().__init__()
        self.close_error = close_error

    def close(self) -> None:
        if not self.closed:
            self.data = self.getvalue()
        super().close()
        if self.close_error is not None:
            raise self.close_error


class FakeFfmpeg:
    """Stands in for the overlay's ffmpeg process."""

    def __init__(self, exit_code: int = 0, close_error: OSError | None = None) -> None:
        self.stdin = FakePipe(close_error)
        self.exit_code = exit_code
        self.killed = False

    def wait(self) -> int:
        return -9 if self.killed else self.exit_code

    def kill(self) -> None:
        self.killed = True
