# Saathi — Windows help, one simple step at a time

**Author:** [Add your name(s)]  
**GitHub:** https://github.com/animeshmisra2008/Sarvam-AI-Project

## What It Does

Saathi is a voice-first Windows guide for older adults and people who are new to computers. A user describes what they want to do, and Saathi explains the task in small, clear steps with spoken guidance.

- **Voice Assistance:** Speak a request and hear each instruction aloud.
- **Step-by-Step Guidance:** Breaks everyday Windows tasks into one action at a time, with a clear highlighted step.
- **Screen Guidance:** Select an open app window and Saathi highlights the next button on screen. After each click, it checks the updated window and guides the next action.
- **Type Instead:** Hold the edge launcher to type a request.
- **Language Choice:** Guidance is available in English, Hindi, Bengali, Tamil, Telugu, Kannada, Malayalam, Marathi, Gujarati, Punjabi, and Odia.

Screen guidance sends an image of the selected window to Sarvam when guidance starts and after clicks. Saathi does not save the screenshots or continuously record the screen.

## Tech Stack  

Python, Tkinter, Sarvam AI (`sarvam-105b-conversations`, Saaras, Gemma 4, and Bulbul), sounddevice, and Pillow.

## Goal

Make everyday computer tasks easier to understand and complete for people who may feel unsure using Windows. Saathi provides patient, spoken directions and points to the next button while leaving each action in the user’s hands.

## Run It

1. Install the packages with `python -m pip install -r requirements.txt`.
2. Add your Sarvam key to `.env` as `SARVAM_API_KEY=...`.
3. Run `python saathi.py`.
