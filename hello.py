from flask import Flask, render_template, url_for, request, send_file, Response
from fileinput import filename
from io import BytesIO
import io, shutil, os, glob
from dubber import dub

app = Flask(__name__)

baseName = None
f = None
translate_lang = None

@app.route('/', methods = ['POST', 'GET'])
def index():
  global video_data
  if request.method == "POST":
    global baseName, f, translate_lang
    f = request.files['file']
    translate_lang = request.form.get('lang')
    voice = request.form.get('voice')
    filename = f.filename
    f.save('video/' + filename)
    dub('video/' + filename, 'static/outdir', 'en-IN', [translate_lang], storageBucket=None, phraseHints=[], dubSrc=False, speakerCount=1, voices={translate_lang: f"{translate_lang}-Standard-{voice}"})
    baseName = filename.split('.')[0]
    return render_template('video-preview.html', filename = baseName + f"[{translate_lang}]")
  else:
    try:
      shutil.rmtree('static/outdir')
    except:
      pass

    try:
      files = glob.glob('video/*')
      for f in files:
        os.remove(f)
    except:
      pass
    
    return render_template('index.html')


@app.route('/download', methods = ['POST', 'GET'])
def download():
  global baseName, f, translate_lang
  return send_file(f"static/outdir/dubbedVideos/{baseName}[{translate_lang}].mp4", as_attachment=True, download_name=f"{baseName}[{translate_lang}].mp4")

if __name__ == '__main__':
  app.run(debug = True, port=3000)