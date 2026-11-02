"""Saathi: a small, voice-first Windows helper for everyday computer tasks."""

import base64
import json
import os
import tempfile
import threading
import time
import wave
import winsound
from pathlib import Path
from tkinter import messagebox, ttk
import tkinter as tk

import sounddevice as sd
from sarvamai import SarvamAI


ROOT = Path(__file__).resolve().parent
COLORS = {
    "background": "#F4F6FA",
    "surface": "#FFFFFF",
    "ink": "#18304B",
    "muted": "#52677F",
    "blue": "#155EEF",
    "blue_light": "#E8F0FF",
    "yellow": "#FFF1B8",
    "green": "#E3F5EA",
    "border": "#D7E0EA",
}

LANGUAGES = {
    "English": ("en-IN", "ratan"),
    "हिन्दी (Hindi)": ("hi-IN", "shubh"),
    "বাংলা (Bengali)": ("bn-IN", "rehan"),
    "தமிழ் (Tamil)": ("ta-IN", "ratan"),
    "తెలుగు (Telugu)": ("te-IN", "shubh"),
    "ಕನ್ನಡ (Kannada)": ("kn-IN", "shubh"),
    "മലയാളം (Malayalam)": ("ml-IN", "shubh"),
    "मराठी (Marathi)": ("mr-IN", "ratan"),
    "ગુજરાતી (Gujarati)": ("gu-IN", "ratan"),
    "ਪੰਜਾਬੀ (Punjabi)": ("pa-IN", "mani"),
    "ଓଡ଼ିଆ (Odia)": ("od-IN", "shubh"),
}
LANGUAGE_BY_CODE = {info[0]: name for name, info in LANGUAGES.items()}

SYSTEM_PROMPT = """You are Saathi, a patient guide for people who are new to Windows 11.
Explain the requested computer task as 3 to 7 small, safe steps in the selected language.
Use short, familiar words. Give exactly one action per step. Name visible buttons and
menus when you can. Never claim you can see the user's screen. If an exact label may
vary, say what to look for. If the request is ambiguous, make the first step a simple
question. Do not ask for or guide entry of passwords, PINs, one-time codes, banking
details, or remote access. Do not suggest deleting files, installing unknown software,
or changing security settings.
Return only valid JSON in this shape:
{"title":"short task name","steps":[{"heading":"short action","instruction":"one clear action"}]}"""


def load_api_key():
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "SARVAM_API_KEY":
            os.environ.setdefault("SARVAM_API_KEY", value.strip().strip("\"'"))
            break
    key = os.getenv("SARVAM_API_KEY")
    if not key:
        raise RuntimeError("Add your Sarvam key to .env as SARVAM_API_KEY=... then reopen Saathi.")
    return key


class SaathiApp(tk.Tk):
    PANEL_WIDTH = 440
    PANEL_HEIGHT = 660
    HOLD_TO_TYPE_MS = 650

    def __init__(self):
        super().__init__()
        self.client = SarvamAI(api_subscription_key=load_api_key(), timeout=30.0)
        self.title("Saathi")
        self.configure(bg=COLORS["blue"])
        self.geometry("68x68")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self._position_launcher()

        self.panel = None
        self.panel_body = None
        self.panel_open = False
        self.language_var = tk.StringVar(value="English")
        self.task = ""
        self.task_title = ""
        self.steps = []
        self.step_index = 0
        self.help_text = ""
        self.status_label = None
        self.busy = False
        self.recording = False
        self.recording_stop = None
        self.recording_cancelled = False
        self.hold_after = None
        self.hold_fired = False
        self.audio_path = None
        self.audio_token = 0

        self._draw_launcher()
        menu = tk.Menu(self, tearoff=False, font=("Segoe UI", 11))
        menu.add_command(label="Quit Saathi", command=self.quit_app)
        self.context_menu = menu
        self.bind("<Button-3>", self._show_context_menu)

    def _position_launcher(self):
        x = self.winfo_screenwidth() - 74
        y = (self.winfo_screenheight() - 68) // 2
        self.geometry(f"68x68+{x}+{y}")

    def _draw_launcher(self):
        canvas = tk.Canvas(self, width=68, height=68, bg=COLORS["blue"],
                           highlightthickness=0, cursor="hand2")
        canvas.pack(fill="both", expand=True)
        canvas.create_oval(5, 5, 63, 63, fill=COLORS["blue"], outline="white", width=2)
        canvas.create_text(34, 32, text="S", fill="white", font=("Segoe UI", 22, "bold"))
        canvas.create_oval(25, 45, 29, 49, fill="white", outline="white")
        canvas.create_oval(33, 45, 37, 49, fill="white", outline="white")
        canvas.create_oval(41, 45, 45, 49, fill="white", outline="white")
        canvas.bind("<ButtonPress-1>", self._launcher_pressed)
        canvas.bind("<ButtonRelease-1>", self._launcher_released)
        canvas.bind("<Button-3>", self._show_context_menu)

    def _show_context_menu(self, event):
        self.context_menu.tk_popup(event.x_root, event.y_root)

    def _launcher_pressed(self, _event):
        self.hold_fired = False
        self.hold_after = self.after(self.HOLD_TO_TYPE_MS, self._hold_for_type)

    def _hold_for_type(self):
        self.hold_fired = True
        self.hold_after = None
        self.open_panel("type")

    def _launcher_released(self, _event):
        if self.hold_after is not None:
            self.after_cancel(self.hold_after)
            self.hold_after = None
        if self.hold_fired:
            return
        if self.panel_open:
            if self.recording:
                self.stop_recording()
            else:
                self.close_panel()
        else:
            self.open_panel("voice")

    def open_panel(self, mode):
        if mode == "type" and self.recording:
            self.recording_cancelled = True
            if self.recording_stop:
                self.recording_stop.set()
        self.panel_open = True
        if self.panel is None or not self.panel.winfo_exists():
            self.panel = tk.Toplevel(self)
            self.panel.configure(bg=COLORS["background"])
            self.panel.overrideredirect(True)
            self.panel.attributes("-topmost", True)
            self.panel.geometry(self._panel_geometry())
            self.panel.bind("<Escape>", lambda _event: self.close_panel())
            self.panel_body = tk.Frame(self.panel, bg=COLORS["background"], padx=20, pady=18)
            self.panel_body.pack(fill="both", expand=True)
        else:
            self.panel.geometry(self._panel_geometry())
            self.panel.deiconify()
            self.panel.lift()
        self._show_home(mode)
        if mode == "voice":
            self.start_recording()

    def _panel_geometry(self):
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(self.PANEL_WIDTH, screen_w - 84)
        height = min(self.PANEL_HEIGHT, screen_h - 24)
        x = screen_w - width - 74
        y = max(12, (screen_h - height) // 2)
        return f"{width}x{height}+{x}+{y}"

    def close_panel(self):
        if self.recording:
            self.recording_cancelled = True
            if self.recording_stop:
                self.recording_stop.set()
        if self.panel and self.panel.winfo_exists():
            self.panel.withdraw()
        self.panel_open = False
        self.audio_token += 1
        winsound.PlaySound(None, winsound.SND_PURGE)

    def _clear_panel(self):
        for child in self.panel_body.winfo_children():
            child.destroy()

    def _panel_header(self, subtitle):
        top = tk.Frame(self.panel_body, bg=COLORS["background"])
        top.pack(fill="x", pady=(0, 14))
        brand = tk.Frame(top, bg=COLORS["background"])
        brand.pack(side="left")
        tk.Label(brand, text="Saathi", font=("Segoe UI", 18, "bold"),
                 fg=COLORS["blue"], bg=COLORS["background"]).pack(anchor="w")
        tk.Label(brand, text=subtitle, font=("Segoe UI", 10),
                 fg=COLORS["muted"], bg=COLORS["background"]).pack(anchor="w")
        tk.Button(top, text="×", command=self.close_panel, font=("Segoe UI", 17),
                  width=2, bg=COLORS["background"], fg=COLORS["muted"],
                  activebackground=COLORS["border"], relief="flat", cursor="hand2").pack(side="right")

    def _language_row(self):
        row = tk.Frame(self.panel_body, bg=COLORS["background"])
        row.pack(fill="x", pady=(3, 14))
        tk.Label(row, text="Guidance language", font=("Segoe UI", 11, "bold"),
                 fg=COLORS["ink"], bg=COLORS["background"]).pack(side="left", padx=(0, 8))
        style = ttk.Style(self)
        style.configure("Saathi.TCombobox", font=("Segoe UI", 11), padding=5)
        picker = ttk.Combobox(row, textvariable=self.language_var, values=list(LANGUAGES),
                              state="readonly", style="Saathi.TCombobox", width=21)
        picker.pack(side="left", fill="x", expand=True)

    def _show_home(self, mode):
        self._clear_panel()
        self._panel_header("Your computer helper")
        tk.Label(self.panel_body, text="How can I help?", font=("Segoe UI", 21, "bold"),
                 fg=COLORS["ink"], bg=COLORS["background"]).pack(anchor="w", pady=(2, 4))
        tk.Label(self.panel_body,
                 text="Tell me what you want to do. I’ll guide you one small step at a time.",
                 font=("Segoe UI", 12), fg=COLORS["muted"], bg=COLORS["background"],
                 wraplength=390, justify="left").pack(anchor="w", pady=(0, 12))
        self._language_row()

        if mode == "voice":
            panel = tk.Frame(self.panel_body, bg=COLORS["surface"], padx=18, pady=22,
                             highlightthickness=1, highlightbackground=COLORS["border"])
            panel.pack(fill="x", pady=(0, 10))
            self.voice_status = tk.Label(panel, text="Starting the microphone…",
                                         font=("Segoe UI", 16, "bold"), fg=COLORS["ink"],
                                         bg=COLORS["surface"], wraplength=350)
            self.voice_status.pack(anchor="w")
            tk.Label(panel, text="Speak naturally. Tap “Done speaking” when you’re finished.",
                     font=("Segoe UI", 11), fg=COLORS["muted"],
                     bg=COLORS["surface"], wraplength=350, justify="left").pack(anchor="w", pady=(7, 0))
            tk.Label(panel, text="Your recording is sent to Sarvam to understand your request.",
                     font=("Segoe UI", 9), fg=COLORS["muted"],
                     bg=COLORS["surface"], wraplength=350, justify="left").pack(anchor="w", pady=(7, 0))
            buttons = tk.Frame(self.panel_body, bg=COLORS["background"])
            buttons.pack(fill="x", pady=(8, 12))
            self.start_listening_button = tk.Button(buttons, text="Start listening", command=self.start_recording,
                      font=("Segoe UI", 12), padx=12, pady=9,
                      bg=COLORS["surface"], fg=COLORS["ink"], relief="solid", bd=1,
                      cursor="hand2")
            self.start_listening_button.pack(fill="x", pady=(0, 6))
            self.done_speaking_button = tk.Button(buttons, text="Done speaking", command=self.stop_recording,
                      font=("Segoe UI", 14, "bold"), padx=12, pady=12,
                      bg=COLORS["blue"], fg="white", activebackground="#0B4ACB",
                      activeforeground="white", relief="flat", cursor="hand2")
            self.done_speaking_button.pack(fill="x")
            tk.Button(self.panel_body, text="Type instead", command=self._switch_to_typing,
                      font=("Segoe UI", 12), padx=12, pady=10,
                      bg=COLORS["surface"], fg=COLORS["ink"], relief="solid", bd=1,
                      cursor="hand2").pack(fill="x")
        else:
            tk.Label(self.panel_body, text="Type what you need help with:",
                     font=("Segoe UI", 12, "bold"), fg=COLORS["ink"],
                     bg=COLORS["background"]).pack(anchor="w", pady=(2, 6))
            self.task_entry = tk.Text(self.panel_body, height=4, wrap="word",
                                      font=("Segoe UI", 14), padx=10, pady=9,
                                      relief="solid", bd=1, highlightthickness=2,
                                      highlightbackground=COLORS["border"],
                                      highlightcolor=COLORS["blue"])
            self.task_entry.pack(fill="x", pady=(0, 12))
            self.task_entry.focus_set()
            tk.Button(self.panel_body, text="Show me step by step", command=self.start_typed_task,
                      font=("Segoe UI", 14, "bold"), padx=12, pady=13,
                      bg=COLORS["blue"], fg="white", activebackground="#0B4ACB",
                      activeforeground="white", relief="flat", cursor="hand2").pack(fill="x")
            tk.Button(self.panel_body, text="Use my voice", command=self._switch_to_voice,
                      font=("Segoe UI", 12), padx=12, pady=10,
                      bg=COLORS["surface"], fg=COLORS["ink"], relief="solid", bd=1,
                      cursor="hand2").pack(fill="x", pady=(8, 0))

        self.status_label = tk.Label(self.panel_body, text="",
                                     font=("Segoe UI", 10), fg=COLORS["muted"],
                                     bg=COLORS["background"], wraplength=390, justify="left")
        self.status_label.pack(anchor="w", pady=(12, 0))

    def _switch_to_typing(self):
        if self.recording:
            self.recording_cancelled = True
            if self.recording_stop:
                self.recording_stop.set()
        self._show_home("type")

    def _switch_to_voice(self):
        self._show_home("voice")
        self.start_recording()

    def start_recording(self):
        if self.busy or self.recording:
            return
        self.busy = True
        self.recording = True
        self.recording_cancelled = False
        self.recording_stop = threading.Event()
        if getattr(self, "start_listening_button", None) and self.start_listening_button.winfo_exists():
            self.start_listening_button.pack_forget()
        if getattr(self, "done_speaking_button", None) and self.done_speaking_button.winfo_exists():
            self.done_speaking_button.configure(state="normal", text="Done speaking")
        if getattr(self, "voice_status", None) and self.voice_status.winfo_exists():
            self.voice_status.configure(text="Listening now…")

        def capture():
            chunks = []
            try:
                sample_rate = int(sd.query_devices(kind="input")["default_samplerate"])
                started = time.monotonic()
                with sd.InputStream(samplerate=sample_rate, channels=1, dtype="int16") as stream:
                    while not self.recording_stop.is_set() and time.monotonic() - started < 25:
                        chunk, _overflowed = stream.read(1024)
                        chunks.append(chunk.tobytes())
                if time.monotonic() - started >= 25:
                    self.after(0, lambda: self._set_status("Preparing your request…"))
                if not chunks:
                    raise RuntimeError("No microphone audio was captured.")
                handle, path = tempfile.mkstemp(suffix=".wav", prefix="saathi-mic-")
                os.close(handle)
                with wave.open(path, "wb") as audio_file:
                    audio_file.setnchannels(1)
                    audio_file.setsampwidth(2)
                    audio_file.setframerate(sample_rate)
                    audio_file.writeframes(b"".join(chunks))
                self.after(0, lambda: self._recording_finished(path, None))
            except Exception as exc:
                self.after(0, lambda error=exc: self._recording_finished(None, error))

        threading.Thread(target=capture, daemon=True).start()

    def stop_recording(self):
        if self.recording and self.recording_stop:
            if getattr(self, "done_speaking_button", None) and self.done_speaking_button.winfo_exists():
                self.done_speaking_button.configure(state="disabled", text="Preparing your request…")
            if getattr(self, "voice_status", None) and self.voice_status.winfo_exists():
                self.voice_status.configure(text="Recording received. Sending it to Sarvam…")
            self._set_status("Transcribing your spoken words…")
            self.recording_stop.set()

    def _recording_finished(self, path, error):
        self.recording = False
        self.recording_stop = None
        self.busy = False
        if self.recording_cancelled:
            if path:
                Path(path).unlink(missing_ok=True)
            return
        if error:
            if self.status_label and self.status_label.winfo_exists():
                self.status_label.configure(text="I couldn't use the microphone. Check its permission, or hold the Saathi icon to type.")
            if getattr(self, "voice_status", None) and self.voice_status.winfo_exists():
                self.voice_status.configure(text="Microphone unavailable. Check its permission, then try again or type instead.")
            self._show_listen_again()
            return
        if not path or Path(path).stat().st_size < 64:
            self._set_status("I didn't hear anything. Try speaking again, or hold the icon to type.")
            self._show_listen_again()
            return
        self._set_voice_progress("Transcribing your spoken words…")
        language_name = self.language_var.get()

        def transcribe_and_guide():
            with open(path, "rb") as audio_file:
                speech = self.client.speech_to_text.transcribe(
                    file=audio_file, model="saaras:v4", mode="transcribe",
                    request_options={"timeout_in_seconds": 30, "max_retries": 0})
            transcript = speech.transcript.strip()
            detected = getattr(speech, "language_code", None)
            if not transcript:
                raise ValueError("I didn't catch that. Please try speaking again.")
            response_language = LANGUAGE_BY_CODE.get(detected, language_name)
            preview = transcript if len(transcript) <= 100 else transcript[:97] + "…"
            self.after(0, lambda: self._set_voice_progress(
                f'I heard: “{preview}”\nPreparing clear steps…'))
            title, steps = self._make_steps(transcript, response_language)
            return title, steps, transcript, detected

        def complete(result):
            Path(path).unlink(missing_ok=True)
            title, steps, transcript, detected = result
            if detected in LANGUAGE_BY_CODE:
                self.language_var.set(LANGUAGE_BY_CODE[detected])
            self._show_steps(title, steps, transcript)

        def failed(exc):
            Path(path).unlink(missing_ok=True)
            self._show_home("voice")
            self._set_status(self._friendly_error(exc))
            self._show_listen_again()

        self._run_background(transcribe_and_guide, complete, failed)

    def start_typed_task(self):
        if self.busy:
            return
        task = self.task_entry.get("1.0", "end").strip()
        if not task:
            self._set_status("Type what you need help with first.")
            return
        self._set_status("Preparing your steps…")
        self._run_background(
            lambda: self._make_steps(task, self.language_var.get()),
            lambda result: self._show_steps(result[0], result[1], task),
            self._task_failed,
        )

    def _make_steps(self, task, language_name):
        language_code = LANGUAGES[language_name][0]
        response = self.client.chat.completions(
            model="sarvam-105b-conversations",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + f"\nWrite all guidance in {language_name} ({language_code})."},
                {"role": "user", "content": task},
            ],
            temperature=0.2,
            max_tokens=1400,
            request_options={"timeout_in_seconds": 30, "max_retries": 0},
        )
        content = response.choices[0].message.content.strip()
        start, end = content.find("{"), content.rfind("}")
        if start < 0 or end < start:
            raise ValueError("I couldn't prepare those steps. Please try asking another way.")
        data = json.loads(content[start:end + 1])
        steps = data.get("steps", [])
        if not 1 <= len(steps) <= 9:
            raise ValueError("The guide returned an unexpected number of steps. Please try again.")
        clean_steps = []
        for item in steps:
            heading = str(item.get("heading", "")).strip()
            instruction = str(item.get("instruction", "")).strip()
            if heading and instruction:
                clean_steps.append({"heading": heading, "instruction": instruction})
        if not clean_steps:
            raise ValueError("I couldn't prepare those steps. Please try again.")
        return str(data.get("title") or task), clean_steps

    def _run_background(self, action, on_success, on_error):
        if self.busy:
            return
        self.busy = True

        def worker():
            try:
                result = action()
            except Exception as exc:
                self.after(0, lambda error=exc: self._finish_error(on_error, error))
            else:
                self.after(0, lambda: self._finish_success(on_success, result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_success(self, callback, result):
        self.busy = False
        callback(result)

    def _finish_error(self, callback, error):
        self.busy = False
        callback(error)

    def _task_failed(self, error):
        self._show_home("type")
        self._set_status(self._friendly_error(error))

    def _show_steps(self, title, steps, task):
        self.task = task
        self.task_title = title
        self.steps = steps
        self.step_index = 0
        self.help_text = ""
        self._render_step()

    def _render_step(self):
        self._clear_panel()
        self.audio_token += 1
        token = self.audio_token
        winsound.PlaySound(None, winsound.SND_PURGE)
        self._panel_header("One small step at a time")
        tk.Label(self.panel_body, text=self.task_title, font=("Segoe UI", 16, "bold"),
                 fg=COLORS["ink"], bg=COLORS["background"], wraplength=390,
                 justify="left").pack(anchor="w", pady=(0, 10))

        progress = tk.Frame(self.panel_body, bg=COLORS["background"])
        progress.pack(fill="x", pady=(0, 12))
        for index, _step in enumerate(self.steps):
            active = index == self.step_index
            completed = index < self.step_index
            color = COLORS["yellow"] if active else COLORS["green"] if completed else COLORS["surface"]
            text = "✓" if completed else str(index + 1)
            tk.Label(progress, text=text, width=3, font=("Segoe UI", 12, "bold"),
                     fg=COLORS["ink"], bg=color, padx=4, pady=5,
                     highlightthickness=2 if active else 1,
                     highlightbackground=COLORS["blue"] if active else COLORS["border"]).pack(side="left", padx=(0, 5))
        tk.Label(progress, text=f"Step {self.step_index + 1} of {len(self.steps)}",
                 font=("Segoe UI", 11, "bold"), fg=COLORS["blue"],
                 bg=COLORS["background"]).pack(side="right")

        step = self.steps[self.step_index]
        card = tk.Frame(self.panel_body, bg=COLORS["yellow"], padx=18, pady=18,
                        highlightthickness=2, highlightbackground="#E7C64F")
        card.pack(fill="both", expand=True)
        tk.Label(card, text=step["heading"], font=("Segoe UI", 20, "bold"),
                 fg=COLORS["ink"], bg=COLORS["yellow"], wraplength=360,
                 justify="left").pack(anchor="w", pady=(0, 10))
        tk.Label(card, text=step["instruction"], font=("Segoe UI", 16),
                 fg=COLORS["ink"], bg=COLORS["yellow"], wraplength=360,
                 justify="left", anchor="nw").pack(anchor="w", fill="both", expand=True)
        if self.help_text:
            tk.Label(card, text=self.help_text, font=("Segoe UI", 13),
                     fg=COLORS["ink"], bg=COLORS["yellow"], wraplength=360,
                     justify="left").pack(anchor="w", pady=(10, 0))

        tk.Button(self.panel_body, text="🔊  Hear this step again",
                  command=self.read_current_step,
                  font=("Segoe UI", 12, "bold"), padx=10, pady=9,
                  bg=COLORS["blue_light"], fg=COLORS["ink"], relief="flat",
                  cursor="hand2").pack(fill="x", pady=(10, 4))
        nav = tk.Frame(self.panel_body, bg=COLORS["background"])
        nav.pack(fill="x", pady=(6, 0))
        tk.Button(nav, text="Previous", command=self.previous_step,
                  state="normal" if self.step_index > 0 else "disabled",
                  font=("Segoe UI", 11), padx=10, pady=9,
                  bg=COLORS["surface"], fg=COLORS["ink"], relief="solid", bd=1).pack(side="left")
        tk.Button(nav, text="Explain again", command=self.ask_for_help,
                  font=("Segoe UI", 11), padx=10, pady=9,
                  bg=COLORS["surface"], fg=COLORS["ink"], relief="solid", bd=1,
                  cursor="hand2").pack(side="left", padx=6)
        is_last = self.step_index == len(self.steps) - 1
        tk.Button(nav, text="Finish" if is_last else "Done →",
                  command=self.finish_task if is_last else self.next_step,
                  font=("Segoe UI", 12, "bold"), padx=12, pady=10,
                  bg=COLORS["blue"], fg="white", activebackground="#0B4ACB",
                  activeforeground="white", relief="flat", cursor="hand2").pack(side="right")

        self.status_label = tk.Label(self.panel_body, text="",
                                     font=("Segoe UI", 9), fg=COLORS["muted"],
                                     bg=COLORS["background"], wraplength=390, justify="left")
        self.status_label.pack(anchor="w", pady=(8, 0))
        self.after(220, lambda: self._speak_step_if_current(token))

    def _speak_step_if_current(self, token):
        if token == self.audio_token and self.panel_open:
            self.read_current_step()

    def _set_status(self, text):
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.configure(text=text)

    def _set_voice_progress(self, text):
        self._set_status(text)
        if getattr(self, "voice_status", None) and self.voice_status.winfo_exists():
            self.voice_status.configure(text=text)

    def _show_listen_again(self):
        if getattr(self, "start_listening_button", None) and self.start_listening_button.winfo_exists():
            self.start_listening_button.pack(fill="x", pady=(0, 6))
        if getattr(self, "done_speaking_button", None) and self.done_speaking_button.winfo_exists():
            self.done_speaking_button.pack_forget()

    @staticmethod
    def _friendly_error(error):
        status = getattr(error, "status_code", None)
        if status == 402:
            return "Sarvam API credits are exhausted. Check your Sarvam account, or hold the icon to type later."
        if status == 403:
            return "Sarvam rejected the API key. Check the key in .env."
        if status == 429:
            return "Sarvam is busy right now. Please try again in a moment."
        if status in (413, 422):
            return "That recording could not be processed. Try a shorter request."
        if "timeout" in type(error).__name__.lower():
            return "This request took too long. Please try again, or hold the icon to type."
        if isinstance(error, ValueError):
            return str(error)
        if status:
            return f"Sarvam returned an error ({status}). Please try again in a moment."
        return "I couldn't reach Sarvam. Check your internet connection and try again."

    def _speech_text(self):
        step = self.steps[self.step_index]
        text = f"Step {self.step_index + 1}. {step['heading']}. {step['instruction']}"
        if self.help_text:
            text += f" {self.help_text}"
        return text

    def read_current_step(self):
        if self.busy:
            return
        token = self.audio_token
        language_code, speaker = LANGUAGES[self.language_var.get()]
        text = self._speech_text()

        def make_audio():
            response = self.client.text_to_speech.convert(
                text=text, language_code=language_code,
                model="bulbul:v3", speaker=speaker, pace=0.9,
                request_options={"timeout_in_seconds": 30, "max_retries": 0})
            return base64.b64decode(response.audios[0])

        def play(audio_bytes):
            if token != self.audio_token or not self.panel_open:
                return
            if self.audio_path is None:
                handle, self.audio_path = tempfile.mkstemp(suffix=".wav", prefix="saathi-voice-")
                os.close(handle)
            Path(self.audio_path).write_bytes(audio_bytes)
            try:
                winsound.PlaySound(self.audio_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                self._set_status("Playing voice guidance.")
            except RuntimeError:
                self._set_status("Audio couldn't play. You can still read the highlighted step.")

        self._set_status("Preparing voice guidance…")
        self._run_background(make_audio, play,
                             lambda _error: self._set_status("Audio couldn't play. You can still read the highlighted step."))

    def previous_step(self):
        if self.busy:
            return
        if self.step_index > 0:
            self.step_index -= 1
            self.help_text = ""
            self._render_step()

    def next_step(self):
        if self.busy:
            return
        if self.step_index < len(self.steps) - 1:
            self.step_index += 1
            self.help_text = ""
            self._render_step()

    def ask_for_help(self):
        if self.busy:
            return
        language_name = self.language_var.get()
        language_code = LANGUAGES[language_name][0]
        current = self.steps[self.step_index]
        self.help_text = "Getting a simpler explanation…"
        self._render_step()

        def request_help():
            response = self.client.chat.completions(
                model="sarvam-105b-conversations",
                messages=[
                    {"role": "system", "content": (
                        f"Explain the current Windows 11 step more simply in {language_name} ({language_code}). "
                        "Use one or two short sentences. Give one action only. Do not assume you can see the screen. "
                        "Do not ask for passwords, PINs, one-time codes, banking details, or remote access."
                    )},
                    {"role": "user", "content": (
                        f"Task: {self.task}\nCurrent step: {current['heading']}. {current['instruction']}\n"
                        "Please explain this same step in an easier way."
                    )},
                ],
                temperature=0.2,
                max_tokens=240,
            )
            return response.choices[0].message.content.strip()

        def ready(text):
            self.help_text = text
            self._render_step()

        def failed(_error):
            self.help_text = "I couldn't get another explanation. Please try again in a moment."
            self._render_step()

        self._run_background(request_help, ready, failed)

    def finish_task(self):
        winsound.PlaySound(None, winsound.SND_PURGE)
        self._show_home("voice")
        self.start_recording()

    def quit_app(self):
        self.recording_cancelled = True
        if self.recording_stop:
            self.recording_stop.set()
        winsound.PlaySound(None, winsound.SND_PURGE)
        if self.audio_path:
            Path(self.audio_path).unlink(missing_ok=True)
        self.destroy()


if __name__ == "__main__":
    try:
        SaathiApp().mainloop()
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Saathi could not start", str(exc))
        root.destroy()
