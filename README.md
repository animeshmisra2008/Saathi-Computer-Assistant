# Saathi — Windows help, one simple step at a time

**Author:** Animesh Misra

## What It Does

Saathi is a voice-first Windows guide for older adults and people who are new to computers. A user describes what they want to do, and Saathi explains the task in small, clear steps with spoken guidance.

- **Voice Assistance:** Speak a request and hear each instruction aloud.
- **Step-by-Step Guidance:** Breaks everyday Windows tasks into one action at a time, with a clear highlighted step.
- **Current Official Guidance:** Searches public government and recognized product-support websites, checks their page text and available update dates, and shows the sources used.
- **Screen Guidance:** Select an open app window and Saathi highlights the next button on screen. It checks after clicks and major screen changes, then adapts the next action to what is visible.
- **Type Instead:** Hold the edge launcher to type a request.
- **Language Choice:** Guidance is available in English, Hindi, Bengali, Tamil, Telugu, Kannada, Malayalam, Marathi, Gujarati, Punjabi, and Odia.

Saathi sends the user's request to Sarvam to prepare guidance and to DuckDuckGo to find public sources. It reads matching public pages from government sites and recognized product-support sites, and shows the pages it used with available update dates. Screen guidance checks a tiny screen fingerprint locally every 900 ms. It sends a screenshot of the screen to Sarvam when guidance starts, after clicks, and after a major visual change. Saathi does not save screenshots or send the local screen fingerprints.

## Debug Log

Saathi keeps a rotating local log at `%LOCALAPPDATA%\Saathi\logs\saathi-debug.log`. It records task requests, source lookups, concise model evidence notes and decisions, screen checks, highlighted coordinates, spoken directions, and errors. These are short evidence notes, not hidden chain-of-thought. API keys, audio, and screenshot images are never written to the log; common ID, phone, and verification-code number patterns are masked. Right-click the Saathi launcher and choose **Open debug log** to view it.

## Tech Stack  

Python, Tkinter, Sarvam AI (`sarvam-105b-conversations`, Saaras, Gemma 4, and Bulbul), sounddevice, and Pillow.

## Goal

Make everyday computer tasks easier to understand and complete for people who may feel unsure using Windows. Saathi provides patient, spoken directions and points to the next button while leaving each action in the user’s hands.

## Run It

1. Install the packages with `python -m pip install -r requirements.txt`.
2. Add your Sarvam key to `.env` as `SARVAM_API_KEY=...`.
3. Run `python saathi.py`.
