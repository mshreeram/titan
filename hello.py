from flask import Flask, render_template, url_for, request, send_file, Response
from fileinput import filename
from io import BytesIO
import io

app = Flask(__name__)

video_data = None
filename = None

@app.route('/', methods = ['POST', 'GET'])
def index():
  global video_data
  if request.method == "POST":
    global f, filename
    f = request.files['file']
    filename = f.filename
    video_data = BytesIO(f.read())
    video_data.seek(0)
    return render_template('video-preview.html')
  else:
    return render_template('index.html')

@app.route('/video_stream')
def video_stream():
  global video_data
  if video_data is not None:
    print("Video data length:", len(video_data.getvalue()))
    return Response(video_data.getvalue(), mimetype='video/*', content_type='video/*; charset=utf-8')
  return "No video data available."

@app.route('/download', methods = ['POST', 'GET'])
def download():
  global filename, video_data
  return send_file(video_data, as_attachment=True, download_name="translated_" + f.filename)

if __name__ == '__main__':
  app.run(debug = True, port=3000)