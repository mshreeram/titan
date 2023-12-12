from googletrans import Translator
translater = Translator()

def translater_func(text, dest_lang):
  out = translater.translate(text, dest=dest_lang)
  print(out.text)
  return out.text