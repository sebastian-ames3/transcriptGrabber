#!/usr/bin/env python3
"""
YouTube Podcast Transcript Fetcher

This script fetches YouTube transcripts for a specific podcast channel or playlist
over a recent date range (default: last 3 months) for downstream research.

Dependencies:
    pip install google-api-python-client youtube-transcript-api python-dotenv python-dateutil

Usage:
    # Set your API key first
    export YOUTUBE_API_KEY="YOUR_API_KEY_HERE"

    # Run with channel URL
    python fetch_podcast_transcripts.py \\
        --channel-url "https://www.youtube.com/@SomePodcastChannel" \\
        --months-back 3 \\
        --output-dir "./podcast_transcripts" \\
        --min-duration 300

    # Or run with playlist ID
    python fetch_podcast_transcripts.py \\
        --playlist-id "PLxxxxxxxxxxxxx" \\
        --months-back 3
"""

import os
import sys
import re
import csv
import argparse
import time
import random
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from pathlib import Path
from typing import Optional, List, Dict
import json

# Rate limiting configuration
DEFAULT_DELAY_BETWEEN_TRANSCRIPTS = 2  # seconds between each transcript fetch
DEFAULT_BATCH_SIZE = 10  # number of transcripts per batch
DEFAULT_BATCH_PAUSE = 30  # seconds to pause between batches
MAX_RETRIES = 5  # maximum retries for rate-limited requests
INITIAL_BACKOFF = 5  # initial backoff time in seconds

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable
)
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Default output directory
DEFAULT_OUTPUT_DIR = r"C:\Users\14102\Documents\Sebastian Ames\Projects\Moonshots Transcripts"


def resolve_channel_id(youtube, channel_url: str) -> Optional[str]:
    """
    Resolve a YouTube channel URL to a channel ID.

    Args:
        youtube: YouTube API client
        channel_url: Channel URL (e.g., https://www.youtube.com/@ChannelName)

    Returns:
        Channel ID string, or None if not found
    """
    # Extract handle or username from URL
    # Formats:
    # - https://www.youtube.com/@ChannelHandle
    # - https://www.youtube.com/c/ChannelName
    # - https://www.youtube.com/channel/UCxxxxxxxxx (already a channel ID)

    if "/channel/" in channel_url:
        # Already a channel ID
        match = re.search(r'/channel/([^/?]+)', channel_url)
        if match:
            return match.group(1)

    # Extract handle (starting with @) or custom name
    if "/@" in channel_url:
        handle = re.search(r'/@([^/?]+)', channel_url)
        if handle:
            handle = "@" + handle.group(1)
            try:
                # Use search to find channel by handle
                request = youtube.search().list(
                    part="snippet",
                    q=handle,
                    type="channel",
                    maxResults=1
                )
                response = request.execute()

                if response.get('items'):
                    return response['items'][0]['snippet']['channelId']
            except HttpError as e:
                print(f"Error resolving channel handle: {e}")
                return None

    elif "/c/" in channel_url or "/user/" in channel_url:
        # Custom URL or username
        name = re.search(r'/(?:c|user)/([^/?]+)', channel_url)
        if name:
            name = name.group(1)
            try:
                request = youtube.search().list(
                    part="snippet",
                    q=name,
                    type="channel",
                    maxResults=1
                )
                response = request.execute()

                if response.get('items'):
                    return response['items'][0]['snippet']['channelId']
            except HttpError as e:
                print(f"Error resolving channel name: {e}")
                return None

    print(f"Could not parse channel URL: {channel_url}")
    return None


def list_videos(
    youtube,
    channel_id: Optional[str],
    playlist_id: Optional[str],
    published_after: datetime,
    min_duration: Optional[int] = None,
    max_duration: Optional[int] = None
) -> List[Dict]:
    """
    List videos from a channel or playlist with filters.

    Args:
        youtube: YouTube API client
        channel_id: YouTube channel ID (or None if using playlist)
        playlist_id: YouTube playlist ID (or None if using channel)
        published_after: Only include videos published after this datetime
        min_duration: Minimum video duration in seconds (optional)
        max_duration: Maximum video duration in seconds (optional)

    Returns:
        List of video metadata dictionaries
    """
    videos = []

    # Convert datetime to RFC 3339 format for API
    published_after_str = published_after.isoformat()

    try:
        if playlist_id:
            # Fetch videos from playlist
            print(f"Fetching videos from playlist: {playlist_id}")
            next_page_token = None

            while True:
                request = youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                response = request.execute()

                for item in response.get('items', []):
                    video_id = item['contentDetails']['videoId']
                    published_at = item['snippet']['publishedAt']

                    # Check if published after cutoff date
                    pub_datetime = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    if pub_datetime >= published_after:
                        videos.append({
                            'video_id': video_id,
                            'title': item['snippet']['title'],
                            'published_at': published_at,
                            'video_url': f"https://www.youtube.com/watch?v={video_id}"
                        })

                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break

        elif channel_id:
            # Fetch videos from channel using search API
            print(f"Fetching videos from channel: {channel_id}")
            next_page_token = None

            while True:
                request = youtube.search().list(
                    part="snippet",
                    channelId=channel_id,
                    maxResults=50,
                    order="date",
                    publishedAfter=published_after_str,
                    type="video",
                    pageToken=next_page_token
                )
                response = request.execute()

                for item in response.get('items', []):
                    video_id = item['id']['videoId']
                    videos.append({
                        'video_id': video_id,
                        'title': item['snippet']['title'],
                        'published_at': item['snippet']['publishedAt'],
                        'video_url': f"https://www.youtube.com/watch?v={video_id}"
                    })

                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break

        # Fetch video details (duration, privacy status) for all videos
        print(f"Fetching video details for {len(videos)} videos...")
        videos_with_details = []

        # Process in batches of 50 (API limit)
        for i in range(0, len(videos), 50):
            batch = videos[i:i+50]
            video_ids = [v['video_id'] for v in batch]

            request = youtube.videos().list(
                part="contentDetails,status",
                id=','.join(video_ids)
            )
            response = request.execute()

            details_map = {}
            for item in response.get('items', []):
                video_id = item['id']
                duration_iso = item['contentDetails']['duration']
                privacy_status = item['status']['privacyStatus']

                # Parse ISO 8601 duration (e.g., PT1H2M30S)
                duration_seconds = parse_iso_duration(duration_iso)

                details_map[video_id] = {
                    'duration': duration_seconds,
                    'privacy_status': privacy_status
                }

            # Add details to videos
            for video in batch:
                video_id = video['video_id']
                if video_id in details_map:
                    details = details_map[video_id]

                    # Filter by privacy status (public only)
                    if details['privacy_status'] != 'public':
                        continue

                    # Filter by duration
                    duration = details['duration']
                    if min_duration and duration < min_duration:
                        continue
                    if max_duration and duration > max_duration:
                        continue

                    video['duration'] = duration
                    videos_with_details.append(video)

        print(f"Found {len(videos_with_details)} videos matching filters")
        return videos_with_details

    except HttpError as e:
        print(f"Error fetching videos: {e}")
        return []


def parse_iso_duration(duration: str) -> int:
    """
    Parse ISO 8601 duration to seconds.

    Args:
        duration: ISO 8601 duration string (e.g., PT1H2M30S)

    Returns:
        Duration in seconds
    """
    # Remove PT prefix
    duration = duration.replace('PT', '')

    hours = 0
    minutes = 0
    seconds = 0

    # Parse hours
    if 'H' in duration:
        hours_match = re.search(r'(\d+)H', duration)
        if hours_match:
            hours = int(hours_match.group(1))

    # Parse minutes
    if 'M' in duration:
        minutes_match = re.search(r'(\d+)M', duration)
        if minutes_match:
            minutes = int(minutes_match.group(1))

    # Parse seconds
    if 'S' in duration:
        seconds_match = re.search(r'(\d+)S', duration)
        if seconds_match:
            seconds = int(seconds_match.group(1))

    return hours * 3600 + minutes * 60 + seconds


def fetch_transcript_with_retry(video_id: str, max_retries: int = MAX_RETRIES) -> Optional[str]:
    """
    Fetch English transcript for a video with retry logic for rate limiting.

    Args:
        video_id: YouTube video ID
        max_retries: Maximum number of retries for rate-limited requests

    Returns:
        Full transcript text, or None if not available
    """
    backoff = INITIAL_BACKOFF

    for attempt in range(max_retries + 1):
        try:
            # Create API instance
            api = YouTubeTranscriptApi()

            # Try to fetch English transcript (will auto-select best English variant)
            segments = api.fetch(video_id, languages=['en'])

            # Concatenate all text segments
            full_text = ' '.join([segment.text for segment in segments])
            print(f"  [OK] Found English transcript ({len(segments)} segments)")
            return full_text

        except NoTranscriptFound:
            print(f"  [SKIP] No English transcript found")
            return None

        except TranscriptsDisabled:
            print(f"  [SKIP] Transcripts disabled")
            return None

        except VideoUnavailable:
            print(f"  [SKIP] Video unavailable")
            return None

        except Exception as e:
            error_str = str(e).lower()
            # Check if it's a rate limit error (HTTP 429 or similar)
            if '429' in error_str or 'too many requests' in error_str or 'rate' in error_str:
                if attempt < max_retries:
                    # Add jitter to avoid thundering herd
                    jitter = random.uniform(0, backoff * 0.5)
                    wait_time = backoff + jitter
                    print(f"  [RATE LIMITED] Waiting {wait_time:.1f}s before retry ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    backoff *= 2  # Exponential backoff
                    continue
                else:
                    print(f"  [ERROR] Rate limited after {max_retries} retries")
                    return None
            else:
                print(f"  [ERROR] {e}")
                return None

    return None


def sanitize_filename(title: str) -> str:
    """
    Sanitize video title for use in filename.

    Args:
        title: Video title

    Returns:
        Sanitized filename-safe string
    """
    # Convert to lowercase
    title = title.lower()

    # Replace spaces with underscores
    title = title.replace(' ', '_')

    # Remove problematic characters
    title = re.sub(r'[^\w\-_]', '', title)

    # Limit length to 100 characters
    title = title[:100]

    return title


def write_transcript_file(
    video: Dict,
    transcript: str,
    output_dir: Path
) -> str:
    """
    Write transcript to a text file with metadata header.

    Args:
        video: Video metadata dictionary
        transcript: Full transcript text
        output_dir: Output directory path

    Returns:
        Path to written file (relative to output_dir)
    """
    # Parse published date
    published_at = video['published_at']
    pub_datetime = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
    date_str = pub_datetime.strftime('%Y-%m-%d')

    # Create filename
    sanitized_title = sanitize_filename(video['title'])
    filename = f"{date_str}__{video['video_id']}__{sanitized_title}.txt"
    filepath = output_dir / filename

    # Write file with metadata header
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Title: {video['title']}\n")
        f.write(f"Video URL: {video['video_url']}\n")
        f.write(f"Published: {published_at}\n")
        f.write(f"Duration: {video.get('duration', 'Unknown')} seconds\n")
        f.write("\n")
        f.write(transcript)

    return filename


def write_index_csv(videos: List[Dict], output_dir: Path):
    """
    Write master index CSV file.

    Args:
        videos: List of video metadata dictionaries
        output_dir: Output directory path
    """
    index_path = output_dir / "index.csv"

    with open(index_path, 'w', newline='', encoding='utf-8') as f:
        fieldnames = [
            'video_id',
            'title',
            'published_at',
            'video_url',
            'duration',
            'has_transcript',
            'transcript_path'
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        writer.writeheader()
        for video in videos:
            writer.writerow({
                'video_id': video['video_id'],
                'title': video['title'],
                'published_at': video['published_at'],
                'video_url': video['video_url'],
                'duration': video.get('duration', ''),
                'has_transcript': video.get('has_transcript', False),
                'transcript_path': video.get('transcript_path', '')
            })

    print(f"\nWrote index to: {index_path}")


def main():
    """Main function to orchestrate transcript fetching."""
    parser = argparse.ArgumentParser(
        description='Fetch YouTube transcripts for a podcast channel or playlist'
    )
    parser.add_argument(
        '--channel-url',
        help='YouTube channel URL (e.g., https://www.youtube.com/@ChannelName)'
    )
    parser.add_argument(
        '--playlist-id',
        help='YouTube playlist ID'
    )
    parser.add_argument(
        '--months-back',
        type=int,
        default=3,
        help='Number of months to look back from today (default: 3)'
    )
    parser.add_argument(
        '--output-dir',
        default=DEFAULT_OUTPUT_DIR,
        help=f'Output directory for transcripts (default: {DEFAULT_OUTPUT_DIR})'
    )
    parser.add_argument(
        '--min-duration',
        type=int,
        help='Minimum video duration in seconds (e.g., 300 for 5 minutes)'
    )
    parser.add_argument(
        '--max-duration',
        type=int,
        help='Maximum video duration in seconds'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f'Number of transcripts to fetch per batch (default: {DEFAULT_BATCH_SIZE})'
    )
    parser.add_argument(
        '--batch-pause',
        type=int,
        default=DEFAULT_BATCH_PAUSE,
        help=f'Seconds to pause between batches (default: {DEFAULT_BATCH_PAUSE})'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=DEFAULT_DELAY_BETWEEN_TRANSCRIPTS,
        help=f'Seconds to wait between each transcript fetch (default: {DEFAULT_DELAY_BETWEEN_TRANSCRIPTS})'
    )

    args = parser.parse_args()

    # Prompt for output directory if not provided via command line
    if args.output_dir == DEFAULT_OUTPUT_DIR:
        print(f"\nDefault output directory: {DEFAULT_OUTPUT_DIR}")
        user_input = input("Enter output directory (or press Enter to use default): ").strip()
        if user_input:
            args.output_dir = user_input

    # Validate inputs
    if not args.channel_url and not args.playlist_id:
        print("Error: Must provide either --channel-url or --playlist-id")
        sys.exit(1)

    if args.channel_url and args.playlist_id:
        print("Error: Provide only one of --channel-url or --playlist-id")
        sys.exit(1)

    # Get API key from environment
    api_key = os.getenv('YOUTUBE_API_KEY')
    if not api_key:
        print("Error: YOUTUBE_API_KEY environment variable not set")
        print("Please set it with: export YOUTUBE_API_KEY='your_api_key_here'")
        sys.exit(1)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")

    # Initialize YouTube API client
    youtube = build('youtube', 'v3', developerKey=api_key)

    # Resolve channel ID if channel URL provided
    channel_id = None
    if args.channel_url:
        print(f"Resolving channel URL: {args.channel_url}")
        channel_id = resolve_channel_id(youtube, args.channel_url)
        if not channel_id:
            print("Error: Could not resolve channel ID from URL")
            sys.exit(1)
        print(f"Channel ID: {channel_id}")

    # Calculate date range
    today = datetime.now(timezone.utc)
    published_after = today - relativedelta(months=args.months_back)
    print(f"Fetching videos published after: {published_after.isoformat()}")

    if args.min_duration:
        print(f"Minimum duration: {args.min_duration} seconds")
    if args.max_duration:
        print(f"Maximum duration: {args.max_duration} seconds")

    # List videos
    videos = list_videos(
        youtube,
        channel_id=channel_id,
        playlist_id=args.playlist_id,
        published_after=published_after,
        min_duration=args.min_duration,
        max_duration=args.max_duration
    )

    if not videos:
        print("No videos found matching the criteria")
        sys.exit(0)

    total_videos = len(videos)
    total_batches = (total_videos + args.batch_size - 1) // args.batch_size

    print(f"\nProcessing {total_videos} videos...")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Total batches: {total_batches}")
    print(f"  Delay between transcripts: {args.delay}s")
    print(f"  Pause between batches: {args.batch_pause}s")

    # Fetch transcripts and write files
    success_count = 0
    skip_count = 0

    for i, video in enumerate(videos, 1):
        video_id = video['video_id']
        title = video['title']
        current_batch = (i - 1) // args.batch_size + 1

        print(f"\n[{i}/{total_videos}] (Batch {current_batch}/{total_batches}) Fetching transcript for: {title}")
        print(f"  Video ID: {video_id}")

        transcript = fetch_transcript_with_retry(video_id)

        if transcript:
            # Write transcript file
            filename = write_transcript_file(video, transcript, output_dir)
            video['has_transcript'] = True
            video['transcript_path'] = filename
            success_count += 1
            print(f"  [OK] Wrote transcript to: {filename}")
        else:
            video['has_transcript'] = False
            video['transcript_path'] = ''
            skip_count += 1
            print(f"  [SKIP] No English transcript available")

        # Rate limiting: delay between requests
        if i < total_videos:
            # Check if we've completed a batch
            if i % args.batch_size == 0:
                print(f"\n{'='*60}")
                print(f"Batch {current_batch}/{total_batches} complete. Pausing for {args.batch_pause} seconds...")
                print(f"Progress: {success_count} downloaded, {skip_count} skipped")
                print(f"{'='*60}")
                time.sleep(args.batch_pause)
            else:
                # Normal delay between transcripts
                time.sleep(args.delay)

    # Write index CSV
    write_index_csv(videos, output_dir)

    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total videos found: {len(videos)}")
    print(f"Transcripts downloaded: {success_count}")
    print(f"Skipped (no English transcript): {skip_count}")
    print(f"Output directory: {output_dir}")
    print("="*60)


if __name__ == "__main__":
    main()
