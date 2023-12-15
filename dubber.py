from pydub import AudioSegment
from google.cloud import speech_v1p1beta1 as speech
from google.cloud import texttospeech
from google.cloud import translate_v2 as translate
from google.cloud import storage
from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip
from moviepy.video.tools.subtitles import SubtitlesClip, TextClip
import os
import shutil
import ffmpeg
import time
import json
import sys
import tempfile
import uuid
from dotenv import load_dotenv
import fire
import html

# Load config in .env file
load_dotenv()

def extract_audio(videoPath, outputPath):

    AudioSegment.from_file(videoPath).set_channels(1).export(outputPath, format="wav")


# def decode_audio(inFile, outFile):
#     """Converts a video file to a wav file.

#     Args:
#         inFile (String): i.e. my/great/movie.mp4
#         outFile (String): i.e. my/great/movie.wav
#     """
#     if not outFile[-4:] != "wav":
#         outFile += ".wav"
#     AudioSegment.from_file(inFile).set_channels(
#         1).export(outFile, format="wav")


def get_transcripts(cloudPath, langCode, phraseHints=[], speakerCount=1):
    """Transcribes audio files.

    Args:
        cloudPath (String): path to file in cloud storage (i.e. "gs://audio/clip.mp4")
        langCode (String): language code (i.e. "en-US", see https://cloud.google.com/speech-to-text/docs/languages)
        phraseHints (String[]): list of words that are unusual but likely to appear in the audio file.
        speakerCount (int, optional): Number of speakers in the audio. Only works on English. Defaults to None.
        enhancedModel (String, optional): Option to use an enhanced speech model, i.e. "video"

    Returns:
        list | Operation.error
    """

    # Helper function for simplifying Google speech client response
    def jsonify(result):
        json = []
        for section in result.results:
            data = {
                "transcript": section.alternatives[0].transcript,
                "words": []
            }
            for word in section.alternatives[0].words:
                data["words"].append({
                    "word": word.word,
                    "start_time": word.start_time.total_seconds(),
                    "end_time": word.end_time.total_seconds(),
                    "speaker_tag": word.speaker_tag
                })
            json.append(data)
        return json

    client = speech.SpeechClient()  
    audio = speech.RecognitionAudio(uri=cloudPath)

    diarize = speakerCount if speakerCount > 1 else False
    print(f"Diarizing: {diarize}")
    diarizationConfig = speech.SpeakerDiarizationConfig(
        enable_speaker_diarization= diarize,
    )

    # In English only, we can use the optimized video model
    config = speech.RecognitionConfig(
        language_code="en-US" if langCode == "en" else langCode,
        enable_automatic_punctuation=True,
        enable_word_time_offsets=True,
        speech_contexts=[{
            "phrases": phraseHints,
            "boost": 15
        }],
        diarization_config=diarizationConfig,
        profanity_filter=True,
        use_enhanced=True,
        model="video"
    )

    res = client.long_running_recognize(config=config, audio=audio).result()

    return jsonify(res)

def parse_sentence_with_speaker(json, lang):
    """Takes json from get_transcripts and breaks it into sentences
    spoken by a single person. Sentences deliniated by a >= 1 second pause/

    Args:
        json (string[]): [{"transcript": "lalala", "words": [{"word": "la", "start_time": 20, "end_time": 21, "speaker_tag: 2}]}]
        lang (string): language code, i.e. "en"
    Returns:
        string[]: [{"sentence": "lalala", "speaker": 1, "start_time": 20, "end_time": 21}]
    """

    sentences = []
    sentence = {}
    for result in json:
        for i, word in enumerate(result['words']):
            wordText = word['word']
            if not sentence:
                sentence = {
                    lang: [wordText],
                    'speaker': word['speaker_tag'],
                    'start_time': word['start_time'],
                    'end_time': word['end_time']
                }
            # If we have a new speaker, save the sentence and create a new one:
            elif word['speaker_tag'] != sentence['speaker']:
                sentence[lang] = ' '.join(sentence[lang])
                sentences.append(sentence)
                sentence = {
                    lang: [wordText],
                    'speaker': word['speaker_tag'],
                    'start_time': word['start_time'],
                    'end_time': word['end_time']
                }
            else:
                sentence[lang].append(wordText)
                sentence['end_time'] = word['end_time']

            # If there's greater than one second gap, assume this is a new sentence
            if i+1 < len(result['words']) and word['end_time'] < result['words'][i+1]['start_time']:
                sentence[lang] = ' '.join(sentence[lang])
                sentences.append(sentence)
                sentence = {}
        if sentence:
            sentence[lang] = ' '.join(sentence[lang])
            sentences.append(sentence)
            sentence = {}

    return sentences


def translate_text(input, targetLang):
    """Translates from sourceLang to targetLang. If sourceLang is empty,
    it will be auto-detected.

    Args:
        sentence (String): Sentence to translate
        targetLang (String): i.e. "en"
        sourceLang (String, optional): i.e. "es" Defaults to None.

    Returns:
        String: translated text
    """

    translate_client = translate.Client()
    result = translate_client.translate(
        input, target_language=targetLang, source_language="en")

    return html.unescape(result['translatedText'])


def speak(text, languageCode, voiceName=None, speakingRate=1):
    """Converts text to audio

    Args:
        text (String): Text to be spoken
        languageCode (String): Language (i.e. "en")
        voiceName: (String, optional): See https://cloud.google.com/text-to-speech/docs/voices
        speakingRate: (int, optional): speed up or slow down speaking
    Returns:
        bytes : Audio in wav format
    """

    # Instantiates a client
    client = texttospeech.TextToSpeechClient()

    # Set the text input to be synthesized
    synthesis_input = texttospeech.SynthesisInput(text=text)

    # Build the voice request, select the language code ("en-US") and the ssml
    # voice gender ("neutral")
    if not voiceName:
        voice = texttospeech.VoiceSelectionParams(
            language_code=languageCode, ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )
    else:
        voice = texttospeech.VoiceSelectionParams(
            language_code=languageCode, name=voiceName
        )

    # Select the type of audio file you want returned
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speakingRate
    )

    # Perform the text-to-speech request on the text input with the selected
    # voice parameters and audio file type
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    return response.audio_content


def text_to_speech(text, languageCode, durationSecs, voiceName=None):
    """Speak text within a certain time limit.
    If audio already fits within duratinSecs, no changes will be made.

    Args:
        text (String): Text to be spoken
        languageCode (String): language code, i.e. "en"
        durationSecs (int): Time limit in seconds
        voiceName (String, optional): See https://cloud.google.com/text-to-speech/docs/voices

    Returns:
        bytes : Audio in wav format
    """
    baseAudio = speak(text, languageCode, voiceName=voiceName)
    assert len(baseAudio)
    tempfile = tempfile.NamedTemporaryFile(mode="w+b")
    tempfile.write(baseAudio)
    tempfile.flush()
    baseDuration = AudioSegment.from_mp3(tempfile.name).duration_seconds
    tempfile.close()
    ratio = baseDuration / durationSecs

    # if the audio fits, return it
    if ratio <= 1:
        return baseAudio

    # If the base audio is too long to fit in the segment...

    # round to one decimal point and go a little faster to be safe,
    ratio = round(ratio, 1)
    if ratio > 4:
        ratio = 4
    return speak(text, languageCode, voiceName=voiceName, speakingRate=ratio)

def stitch_audio(sentences, audioDir, videoFile, outFile, overlayGain = -30):
    """Combines sentences, audio clips, and video file into the ultimate dubbed video

    Args:
        sentences (list): Output of parse_sentence_with_speaker
        audioDir (String): Directory containing generated audio files to stitch together
        movieFile (String): Path to movie file to dub.
        outFile (String): Where to write dubbed movie.
        srtPath (String, optional): Path to transcript/srt file, if desired.
        overlayGain (int, optional): How quiet to make source audio when overlaying dubs. 
            Defaults to -30.

    Returns:
       void : Writes movie file to outFile path
    """

    # Files in the audioDir should be labeled 0.wav, 1.wav, etc.
    audioFiles = os.listdir(audioDir)
    audioFiles.sort(key=lambda x: int(x.split('.')[0]))

    # Grab the computer-generated audio file
    segments = [AudioSegment.from_mp3(f"{audioDir}/{x}") for x in audioFiles] 
    # Also, grab the original audio
    dubbed = AudioSegment.from_file(videoFile)

    # Place each computer-generated audio at the correct timestamp
    for sentence, segment in zip(sentences, segments):
        dubbed = dubbed.overlay(segment, position=sentence['start_time'] * 1000, gain_during_overlay=overlayGain)

    # Write the final audio to a temporary output file
    audioFile = tempfile.NamedTemporaryFile()
    dubbed.export(audioFile.name)
    audioFile.flush()

    # Add the new audio to the video and save it
    clip = VideoFileClip(videoFile)
    audio = AudioFileClip(audioFile.name)
    clip = clip.set_audio(audio)

    clip.write_videofile(outFile, codec='libx264', audio_codec='aac')
    audioFile.close()

def dub(
        videoPath, outputDir, srcLang, targetLangs=[],
        storageBucket=None, phraseHints=[],
        speakerCount=1, voices={}, genAudio=False):
    """Translate and dub a movie.

    Args:
        videoPath (String): File to dub
        outputDir (String): Directory to write output files
        srcLang (String): Language code to translate from (i.e. "fi")
        targetLangs (list, optional): Languages to translate too, i.e. ["en", "fr"]
        storageBucket (String, optional): GCS bucket for temporary file storage. Defaults to None.
        phraseHints (list, optional): "Hints" for words likely to appear in audio. Defaults to [].
        dubSrc (bool, optional): Whether to generate dubs in the source language. Defaults to False.
        speakerCount (int, optional): How many speakers in the video. Defaults to 1.
        voices (dict, optional): Which voices to use for dubbing, i.e. {"en": "en-AU-Standard-A"}. Defaults to {}.
        srt (bool, optional): Path of SRT transcript file, if it exists. Defaults to False.
        newDir (bool, optional): Whether to start dubbing from scratch or use files in outputDir. Defaults to False.
        genAudio (bool, optional): Generate new audio, even if it's already been generated. Defaults to False.
        noTranslate (bool, optional): Don't translate. Defaults to False.

    Raises:
        void : Writes dubbed video and intermediate files to outputDir
    """

    videoName = os.path.split(videoPath)[-1].split('.')[0]

    if not os.path.exists(outputDir):
        os.mkdir(outputDir)

    outputFiles = os.listdir(outputDir)

    if not f"{videoName}.wav" in outputFiles:
        print("Extracting audio from video")
        outputAudioPath = f"{outputDir}/{videoName}.wav"
        extract_audio(videoPath, outputAudioPath)
        print(f"Wrote {outputAudioPath}")

    if not f"transcript.json" in outputFiles:
        storageBucket = storageBucket if storageBucket else os.environ['STORAGE_BUCKET']
        if not storageBucket:
            raise Exception(
                "Specify variable STORAGE_BUCKET in .env or as an arg")

        print("Transcribing audio")
        print("Uploading to the cloud...")
        storageClient = storage.Client()
        bucket = storageClient.bucket(storageBucket)

        tmpFile = f"tmp/{str(uuid.uuid4())}.wav"
        blob = bucket.blob(tmpFile)

        # Temporary upload audio file to the cloud f"{outputDir}/{videoName}.wav"
        blob.upload_from_filename(f"{outputDir}/{videoName}.wav", content_type="audio/wav")

        print("Transcribing...")
        transcripts = get_transcripts(f"gs://{storageBucket}/{tmpFile}", srcLang, phraseHints=phraseHints, speakerCount=speakerCount)
        print(transcripts)
        json.dump(transcripts, open(f"{outputDir}/transcript.json", "w"))

        sentences = parse_sentence_with_speaker(transcripts, srcLang)
        sentencePath = f"{outputDir}/{videoName}.json"
        with open(sentencePath, "w") as f:
            json.dump(sentences, f)

        print("Deleting cloud file...")
        blob.delete()

    sentences = json.load(open(f"{outputDir}/{videoName}.json"))
    
    for lang in targetLangs:
        print(f"Translating to {lang}")
        for sentence in sentences:
            sentence[lang] = translate_text(sentence[srcLang], lang)
            print(f"text={sentence[lang]}\n")

    # Write the translations to json
    sentencePath = f"{outputDir}/{videoName}.json"
    with open(sentencePath, "w") as f:
        json.dump(sentences, f)

    audioDir = f"{outputDir}/audioClips"
    if not "audioClips" in outputFiles:
        os.mkdir(audioDir)

    for lang in targetLangs:
        languageDir = f"{audioDir}/{lang}"
        # if os.path.exists(languageDir):
        #     if not genAudio:
        #         continue
        #     shutil.rmtree(languageDir)
        # os.mkdir(languageDir)
        print(f"Synthesizing audio for {lang}")
        for i, sentence in enumerate(sentences):
            voiceName = voices[lang] if lang in voices else None
            audio = text_to_speech(sentence[lang], lang, sentence['end_time'] - sentence['start_time'], voiceName=voiceName)

            with open(f"{languageDir}/{i}.mp3", 'wb') as f: 
                f.write(audio)

    dubbedDir = f"{outputDir}/dubbedVideos" 

    if not "dubbedVideos" in outputFiles:
        os.mkdir(dubbedDir)

    for lang in targetLangs:
        print(f"Dubbing audio for {lang}")
        outFile = f"{dubbedDir}/{videoName}[{lang}].mp4"
        stitch_audio(sentences, f"{audioDir}/{lang}", videoPath, outFile) 

    print("Done")