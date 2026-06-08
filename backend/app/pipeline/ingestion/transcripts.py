import logging
from typing import Tuple

import httpx
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

logger = logging.getLogger("pipeline.ingestion.transcripts")

async def fetch_transcript_from_invidious(video_id: str, instance_url: str = "https://yewtu.be") -> str:
    """
    Fallback method: Fetch caption/subtitle tracks from Invidious API.
    """
    api_url = f"{instance_url.rstrip('/')}/api/v1/videos/{video_id}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(api_url)
            if response.status_code == 200:
                video_data = response.json()
                captions = video_data.get("captions", [])
                if captions:
                    # Try to find English captions first, otherwise get first available
                    target_caption = next((c for c in captions if c.get("language_code") == "en"), captions[0])
                    caption_url = target_caption.get("url")
                    if caption_url:
                        # Invidious caption URLs can be relative
                        if caption_url.startswith("/"):
                            caption_url = f"{instance_url.rstrip('/')}{caption_url}"

                        logger.info(f"Fetching subtitle fallbacks from Invidious: {caption_url}")
                        cap_resp = await client.get(caption_url)
                        if cap_resp.status_code == 200:
                            # Caption tracks are usually WebVTT or SRT formatted.
                            # We strip timestamp lines simply using regex/filters to get raw text.
                            raw_lines = cap_resp.text.splitlines()
                            clean_words = []
                            for line in raw_lines:
                                line_stripped = line.strip()
                                # Skip WebVTT headers, timestamp rows, and empty lines
                                if not line_stripped or "-->" in line_stripped or line_stripped.startswith("WEBVTT") or line_stripped.startswith("NOTE"):
                                    continue
                                clean_words.append(line_stripped)
                            return " ".join(clean_words)
    except Exception as e:
        logger.warning(f"Invidious caption fallback failed for {video_id}: {str(e)}")
    return ""

async def fetch_transcript(video_id: str) -> Tuple[str, str, str]:
    """
    Retrieves the transcript/subtitles for a given YouTube video.

    Returns:
        Tuple of (transcript_text, language_code, transcript_source)
    """
    try:
        # 1. Fetch available transcripts list to locate perfect candidate
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try manual English, then generated English
        try:
            transcript = transcript_list.find_transcript(['en'])
            source = "youtube_api_manual" if not transcript.is_generated else "youtube_api_auto"
            logger.info(f"Retrieved English transcript for video {video_id} ({source})")
        except (NoTranscriptFound, TranscriptsDisabled):
            # Try to grab whatever first language is available (multilingual support)
            try:
                # Get the first item in the list
                transcript = next(iter(transcript_list))
                source = f"youtube_api_multilingual_{transcript.language_code}"
                logger.info(f"Retrieved {transcript.language_code} transcript for video {video_id}")
            except Exception:
                raise NoTranscriptFound(video_id, "No transcripts available", transcript_list) from None

        # Pull raw lines
        transcript_data = transcript.fetch()
        full_text = " ".join([t['text'] for t in transcript_data])
        return full_text, transcript.language_code, source

    except Exception as e:
        logger.warning(f"YouTube transcript retrieval failed for {video_id}: {str(e)}")

        # 2. Trigger Invidious Caption fallback
        logger.info(f"Attempting Invidious caption fallback for {video_id}...")
        fallback_text = await fetch_transcript_from_invidious(video_id)
        if fallback_text:
            return fallback_text, "en", "invidious_caption_fallback"

        return "", "en", "failed"
