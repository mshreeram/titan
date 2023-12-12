import subprocess

def generate_final(source_path):
  subprocess.call(['ffmpeg', '-i', source_path, '-vf', 'subtitles=static/outdir/output.srt', 'static/outdir/video_with_subtitles.mp4'])