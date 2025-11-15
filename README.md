# YouTube Transcript Grabber

A production-quality Python script to fetch YouTube transcripts from podcast channels or playlists over a specified date range for downstream research and analysis.

## Features

- ✅ Fetch transcripts from YouTube channels or playlists
- ✅ Filter by date range (default: last 3 months)
- ✅ Filter by video duration (min/max)
- ✅ English transcripts only (strict mode)
- ✅ Public videos only
- ✅ Automatic pagination for large channels
- ✅ CSV index file with all metadata
- ✅ Individual text files per video with metadata headers

## Prerequisites

- Python 3.10 or higher
- YouTube Data API v3 key ([Get one here](https://console.cloud.google.com/apis/credentials))

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd transcriptGrabber
   ```

2. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up your API key:**

   Create a `.env` file in the project root:
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and add your YouTube API key:
   ```
   YOUTUBE_API_KEY=your_api_key_here
   ```

## Usage

### Basic Usage

```bash
# Activate virtual environment (if not already activated)
source venv/bin/activate

# Fetch transcripts from a channel (last 3 months)
python fetch_podcast_transcripts.py \
    --channel-url "https://www.youtube.com/@ChannelName"
```

### Advanced Usage

```bash
# Fetch from channel with duration filter (videos > 15 minutes)
python fetch_podcast_transcripts.py \
    --channel-url "https://www.youtube.com/@ChannelName" \
    --months-back 6 \
    --min-duration 900

# Fetch from playlist with custom output directory
python fetch_podcast_transcripts.py \
    --playlist-id "PLxxxxxxxxxxxxx" \
    --months-back 12 \
    --output-dir "./my_transcripts"

# Filter videos between 10 minutes and 2 hours
python fetch_podcast_transcripts.py \
    --channel-url "https://www.youtube.com/@ChannelName" \
    --min-duration 600 \
    --max-duration 7200
```

## Command-Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--channel-url` | YouTube channel URL (e.g., `https://www.youtube.com/@ChannelName`) | Required* |
| `--playlist-id` | YouTube playlist ID | Required* |
| `--months-back` | Number of months to look back from today | `3` |
| `--output-dir` | Directory to save transcripts | Platform-specific** |
| `--min-duration` | Minimum video duration in seconds (e.g., `300` for 5 min) | None |
| `--max-duration` | Maximum video duration in seconds (e.g., `7200` for 2 hours) | None |

\* Either `--channel-url` or `--playlist-id` is required (but not both)

\*\* Default output directory:
- Linux/WSL: `/mnt/c/Users/14102/Documents/Sebastian Ames/Projects/Moonshots Transcripts`
- You can customize this in the script or use `--output-dir`

## Output

### Transcript Files

Each video generates a text file with:
- **Filename format:** `YYYY-MM-DD__VIDEO_ID__sanitized_title.txt`
- **Content:**
  - Metadata header (title, URL, published date, duration)
  - Full transcript text

**Example:**
```
Title: Amazing AI Podcast Episode
Video URL: https://www.youtube.com/watch?v=abc123
Published: 2025-01-15T10:30:00Z
Duration: 3600 seconds

[Transcript text here...]
```

### Index File

A CSV file (`index.csv`) containing all video metadata:

| Column | Description |
|--------|-------------|
| `video_id` | YouTube video ID |
| `title` | Video title |
| `published_at` | Publication date (ISO format) |
| `video_url` | Full YouTube URL |
| `duration` | Duration in seconds |
| `has_transcript` | Boolean (True/False) |
| `transcript_path` | Relative path to transcript file |

## Examples

### Example 1: Tech Podcast

```bash
python fetch_podcast_transcripts.py \
    --channel-url "https://www.youtube.com/@peterdiamandis" \
    --months-back 4 \
    --min-duration 900
```

### Example 2: Educational Playlist

```bash
python fetch_podcast_transcripts.py \
    --playlist-id "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf" \
    --months-back 6
```

## Filtering Logic

The script applies the following filters:

1. ✅ **Date Range:** Only videos published within the last N months
2. ✅ **Privacy:** Public videos only (skips private/unlisted)
3. ✅ **Duration:** Videos matching min/max duration constraints
4. ✅ **Language:** English transcripts only (skips videos without English captions)

## Troubleshooting

### "YOUTUBE_API_KEY environment variable not set"

Make sure you've created a `.env` file with your API key:
```bash
echo "YOUTUBE_API_KEY=your_key_here" > .env
```

### "No videos found matching the criteria"

Try adjusting your filters:
- Increase `--months-back`
- Remove or adjust `--min-duration` and `--max-duration`
- Verify the channel URL is correct

### "No English transcript found"

Some videos may not have English transcripts available. The script will skip these videos and continue processing others.

### API Quota Exceeded

YouTube Data API has daily quotas. If exceeded:
1. Wait 24 hours for quota reset
2. Request quota increase in Google Cloud Console
3. Use multiple API keys (manual rotation)

## Dependencies

- `google-api-python-client` - YouTube Data API v3
- `youtube-transcript-api` - Transcript fetching
- `python-dotenv` - Environment variable management
- `python-dateutil` - Date calculations

## License

MIT License - See LICENSE file for details

## Contributing

Contributions welcome! Please open an issue or submit a pull request.

## Notes

- The script respects YouTube's Terms of Service
- Transcripts are fetched using official APIs only (no scraping)
- Only publicly available data is accessed
- Rate limiting is handled automatically

## Author

Built for research and content analysis purposes.

---

**Happy transcript grabbing! 📝**
