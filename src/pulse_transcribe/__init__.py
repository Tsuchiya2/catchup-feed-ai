"""pulse Phase 2 transcribe worker (§5 / §7).

Polls the Pi's jobs table for kind='transcribe', turns YouTube videos and
podcast episodes into text (subtitles first, faster-whisper as fallback),
and stores the transcript in articles.content. From there the backend's
existing summarize chain takes over.
"""
