# Third-party notices

CampaignScribe includes or downloads the following third-party models and software.

## Bundled with CampaignScribe

### pyannote speaker-diarization-community-1 (pipeline and weights)
- Source: https://huggingface.co/pyannote/speaker-diarization-community-1 (revision 3533c8cf)
- License: Creative Commons Attribution 4.0 International (CC-BY-4.0) — https://creativecommons.org/licenses/by/4.0/
- Copyright: pyannote / pyannoteAI. Redistributed unmodified.
- Components:
  - Segmentation model — pyannote.
  - Speaker-embedding model — WeSpeaker ResNet34 trained on VoxCeleb (copied from pyannote/wespeaker-voxceleb-resnet34-LM); follows the VoxCeleb dataset license, CC-BY-4.0. WeSpeaker: https://github.com/wenet-e2e/wespeaker
  - PLDA / clustering parameters — VBx (Brno University of Technology, Speech@FIT), integrated into pyannote.audio by Jiangyu Han and Petr Pálka.

### pyannote.audio (library)
- License: MIT — https://github.com/pyannote/pyannote-audio

### WhisperX
- License: BSD-2-Clause — https://github.com/m-bain/whisperX
- Redistributes, and CampaignScribe uses, the pyannote `segmentation` model as its voice-activity detector (`whisperx/assets/pytorch_model.bin`): https://huggingface.co/pyannote/segmentation — MIT License, Copyright (c) CNRS, Hervé Bredin.

### faster-whisper / CTranslate2
- faster-whisper: MIT — https://github.com/SYSTRAN/faster-whisper
- CTranslate2: MIT — https://github.com/OpenNMT/CTranslate2

### Python
- License: Python Software Foundation License Version 2 (PSF-2.0) - https://docs.python.org/3/license.html
- Copyright (c) 2001 Python Software Foundation; All Rights Reserved. The official python.org 3.13 distribution is bundled unmodified in the installation folder (`python\`) and runs the app and its first-run setup. Its full license text ships as `python\LICENSE.txt`.

### Inno Setup
- Used to build the CampaignScribe installer; its setup stub is embedded in the installer. https://jrsoftware.org/isinfo.php
- License (Inno Setup License): Copyright (C) 1997-2026 Jordan Russell. Portions Copyright (C) 2000-2026 Martijn Laan. All rights reserved. This software is provided "as-is", without any express or implied warranty. Permission is granted to use it for any purpose, including commercial applications, and to redistribute it provided that the copyright notices and web site addresses are retained and that modified versions are plainly marked as such.

## Downloaded on first use (not bundled)

### OpenAI Whisper models (CTranslate2 conversions by Systran)
- License: MIT — https://github.com/openai/whisper

### wav2vec2 alignment models (via torchaudio)
- License: see https://pytorch.org/audio/stable/pipelines.html

## Citations
- Bredin, H., Laurent, A. "End-to-end speaker segmentation for overlap-aware resegmentation." Interspeech 2021.
- Bredin, H. "pyannote.audio 2.1 speaker diarization pipeline: principle, benchmark, and recipe." Interspeech 2023.
- Wang, H. et al. "Wespeaker: A research and production oriented speaker embedding learning toolkit." ICASSP 2023.
- Landini, F. et al. "Bayesian HMM clustering of x-vector sequences (VBx) in speaker diarization." Computer Speech & Language, 2022.
- Nagrani, A., Chung, J. S., Zisserman, A. "VoxCeleb: a large-scale speaker identification dataset." Interspeech 2017.
