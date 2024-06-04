import os
from io import StringIO
from threading import Lock
from typing import BinaryIO, Union, Tuple

import torch
import whisper
from transformers import pipeline
from whisper.utils import ResultWriter, WriteTXT, WriteSRT, WriteVTT, WriteTSV, WriteJSON

model_name = os.getenv("ASR_MODEL", "large-v3")
model_path = os.getenv("ASR_MODEL_PATH", os.path.join(os.path.expanduser("~"), ".cache", "whisper"))

if torch.cuda.is_available():
    model = whisper.load_model(model_name, download_root=model_path).cuda()
else:
    model = whisper.load_model(model_name, download_root=model_path)
model_lock = Lock()

def transcribe(
        audio,
        task: Union[str, None],
        language: Union[str, None],
        initial_prompt: Union[str, None],
        vad_filter: Union[bool, None],
        word_timestamps: Union[bool, None],
        temperature: Union[float, Tuple[float, ...], None],
        best_of: Union[int, None],
        beam_size: Union[int, None],
        output
):
    options_dict = {"task": task}
    if language:
        options_dict["language"] = language
    if initial_prompt:
        options_dict["initial_prompt"] = initial_prompt
    if word_timestamps:
        options_dict["word_timestamps"] = word_timestamps
    if temperature:
        options_dict["temperature"] = temperature
    if best_of:
        options_dict["best_of"] = best_of
    if beam_size:
        options_dict["beam_size"] = beam_size

    with model_lock:
        result = model.transcribe(audio, **options_dict)

    output_file = StringIO()
    write_result(result, output_file, output)
    output_file.seek(0)

    return result["text"]

def language_detection(audio):
    # load audio and pad/trim it to fit 30 seconds
    audio = whisper.pad_or_trim(audio)

    # make log-Mel spectrogram and move to the same device as the model
    mel = whisper.log_mel_spectrogram(audio).to(model.device)

    # detect the spoken language
    with model_lock:
        _, probs = model.detect_language(mel)
    detected_lang_code = max(probs, key=probs.get)

    return detected_lang_code

def write_result(
        result: dict, file: BinaryIO, output: Union[str, None]
):
    options = {
        'max_line_width': 1000,
        'max_line_count': 10,
        'highlight_words': False
    }
    if output == "srt":
        WriteSRT(ResultWriter).write_result(result, file=file, options=options)
    elif output == "vtt":
        WriteVTT(ResultWriter).write_result(result, file=file, options=options)
    elif output == "tsv":
        WriteTSV(ResultWriter).write_result(result, file=file, options=options)
    elif output == "json":
        WriteJSON(ResultWriter).write_result(result, file=file, options=options)
    elif output == "txt":
        WriteTXT(ResultWriter).write_result(result, file=file, options=options)
    else:
        return 'Please select an output method!'

gpt2_model_name = "gpt2"
gpt2_pipeline = pipeline('text-generation', model=gpt2_model_name, tokenizer=gpt2_model_name, max_new_tokens=50)

def improve_transcription(transcription: str) -> str:
    prompt = f"Popraw transkrypcję: \"{transcription}\". Upewnij się, że tekst jest poprawny gramatycznie i logicznie."
    
    # Generowanie odpowiedzi przez model
    result = gpt2_pipeline(prompt, max_new_tokens=50, num_return_sequences=1)
    
    # Wydobywanie tekstu z wyniku
    improved_transcription = result[0]['generated_text']
    
    # Usunięcie promptu z wygenerowanego tekstu
    improved_transcription = improved_transcription.replace(prompt, "").strip()

    return improved_transcription