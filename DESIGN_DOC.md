# YouTube History Tracker - Design Document

## 1. Motivation
In today's landscape, financial influencers frequently publish videos predicting market movements or promoting specific financial assets. When these predictions fail, influencers have the power to retroactively alter their public track record by deleting videos, changing them to "unlisted" or hidden status, or altering titles and thumbnails to obscure their original assertions. This allows them to create a misleading narrative of high accuracy and outsized achievements.

The **YouTube History Tracker** is designed to hold these content creators accountable. By continuously tracking and scraping targeted YouTube channels—starting initially with the "Primo Rico" channel—this system will preserve historical video metadata (thumbnails, titles, descriptions, and visibility status). By periodically re-scraping and comparing states, we can detect and expose undisclosed narrative changes over time.

## 2. Overall Architecture
The system is composed of several independent components, loosely coupled, allowing for easy expansion and resilient execution:

- **Target Management System**: Maintains the list of channels to monitor. Users can easily register new channels to be watched.
- **Scraping Engine**: A scheduled worker that performs the actual extraction of YouTube channel data. It fetches video lists, titles, descriptions, and downloads thumbnails.
- **Data Persistence Layer (Database)**: An organized data store to maintain channel details, videos, and a historical delta (versioning) of changes for each video.
- **Analysis & Detection Engine**: A core module that compares newly scraped data against the latest saved state to identify deleted, unlisted, or modified videos.
- **Frontend / Dashboard**: An interactive interface allowing users to view the "true" history of a channel, visualize modifications, and see the exact differences between original and modified content.

## 3. Data Storage
Relational databases (like PostgreSQL, or SQLite for an initial prototype) are well-suited for this tracking problem since the data is structured and relation-heavy.

### Proposed Schema Entities:
- **Channels**: `id`, `name`, `youtube_handle`, `created_at`, `status`.
- **Videos**: `video_id`, `channel_id`, `published_at`, `first_seen_at`.
- **Video_Snapshots (The History Versioning)**: `id`, `video_id`, `retrieved_at`, `title`, `description`, `thumbnail_url` (or local storage path), `status` (e.g., PUBLIC, UNLISTED, DELETED, PRIVATE). 
  *Note: A new snapshot is only inserted into the database when the Analysis Engine detects a difference from the most recent snapshot.*
- **Object Storage**: Storing thumbnails locally (or in a cloud bucket like S3) ensures that when a thumbnail is changed on YouTube, we still hold the original visual evidence. Whenever a thumbnail URL changes, a new image is downloaded and linked to the respective Video_Snapshot.

## 4. Scraping, Frequency, and Strategy
The scraping engine needs to balance prompt detection of changes with avoiding rate limits or getting blocked by YouTube.

- **Initial Scrape**: When a channel is newly added, fetch all currently available historical videos to establish a baseline.
- **Periodic Scrape (Active Videos)**: Recent videos are more likely to be edited quickly (e.g., a bad call on an earnings report). The system should scrape recent videos (e.g., those published in the last 3-6 months) more frequently, such as daily or every couple of days.
- **Deep Scrape (Full Archive)**: Older videos might be deleted sporadically when an influencer is doing a "channel cleanup." A full channel sweep should occur less frequently, such as bi-weekly or monthly, to conserve resources and avoid throttling.
- **Implementation Mechanism**: The scraper can be implemented in Python. We can use a combination of the official YouTube Data API v3 and specialized libraries like `yt-dlp` to fetch metadata (without downloading the heavy MP4 video files).

## 5. Adding New Channels
New channels can be added via the Frontend or an Admin Dashboard. 
To add a channel, the user simply inputs the channel handle (e.g., `@OPrimoRico`) or URL. The system will:
1. Resolve and validate the channel handle/ID via YouTube.
2. Insert a new record into the `Channels` table.
3. Queue an immediate **Initial Scrape** task for the scraping engine to populate the baseline data for all existing videos.

## 6. Possible Analysis & Insights
Once the data is populated and changes are detected, the system can provide valuable insights such as:
- **Deletions over Time**: Which topics are most often deleted? Did an influencer delete several videos coincidentally during a specific stock plunge or market crash?
- **Title Sentiments**: Did the influencer alter a title from extremely bullish (e.g., "BUY THIS NOW!") to seemingly neutral (e.g., "Market Analysis") after an asset plummeted?
- **"The Memory Hole" Wall**: Creating a dedicated view highlighting the biggest retractions or "What this influencer doesn't want you to know they said."
- **Response Time**: How quickly does an influencer modify the content after being contradicted by reality?

## 7. Next Steps for Implementation
1. **Initialize the local environment**: Set up the project skeleton and baseline database (e.g., SQLite/PostgreSQL setup).
2. **Implement Target Management & Scraping**: Build the MVP scraper for `@OPrimoRico` capable of extracting metadata and saving thumbnails.
3. **Configure Jobs Architecture**: Setup the scheduling mechanism (using tools like `cron`, `Celery`, or `APScheduler`).
4. **Develop the Versioning Logic**: Write the detection engine to save new `Video_Snapshots` only when metadata differs.
5. **Create the UI/Dashboard**: Develop a web interface (e.g., using Next.js or HTML/JS) to explore the data.
