"""Re-encodes existing MP4 recordings to H.264 so Windows players can open them.

Run with:  python video_transcoder.py
"""

import os
import subprocess

from paths import RECORDINGS_DIR
from video_encoders import CREATE_NO_WINDOW, H264FfmpegEncoder


def video_codec_of(path):
    """Return the codec name of the first video stream, or '' if unknown."""
    ffmpeg = H264FfmpegEncoder.ffmpeg_executable()
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    for line in result.stderr.splitlines():
        if "Video:" in line:
            return line.split("Video:")[1].strip().split()[0].strip(",")
    return ""


def transcode_to_h264(path):
    """Rewrite `path` in place as H.264. Returns True when the file changed."""
    if video_codec_of(path) == "h264":
        return False

    ffmpeg = H264FfmpegEncoder.ffmpeg_executable()
    temp_path = f"{path}.h264.tmp.mp4"
    subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error",
            "-i", path,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "26",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            temp_path,
        ],
        check=True,
        creationflags=CREATE_NO_WINDOW,
    )
    os.replace(temp_path, path)
    return True


def transcode_recordings_folder(folder=RECORDINGS_DIR):
    """Convert every non-H.264 MP4 in `folder`. Returns the converted paths."""
    converted = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith(".mp4"):
            continue
        path = os.path.join(folder, name)
        if transcode_to_h264(path):
            converted.append(path)
    return converted


if __name__ == "__main__":
    for converted_path in transcode_recordings_folder():
        print(f"Converted to H.264: {os.path.basename(converted_path)}")
    print("Done.")
