# Twitter Automatic Login for Extractor

This feature enhances the Twitter extraction process by implementing automatic login with Playwright, ensuring reliable access to tweets without depending on potentially outdated cookies.

## Features

- **Automated Login Process**: Handles the full Twitter login flow using Playwright
- **Session Storage Management**: Saves and reuses browser session state to avoid repeated logins
- **Human-like Behavior**: Implements random delays, mouse movements, and realistic typing patterns
- **CAPTCHA Handling**: Detects CAPTCHA challenges and pauses for manual intervention
- **Seamless Integration**: Works with the existing `TwitterPlaywrightScraper` without major code changes

## Setup

1. **Copy the environment example file**:
   ```bash
   cp .env.example .env
   ```

2. **Fill in your Twitter credentials**:
   Edit the `.env` file with your Twitter username/email and password:
   ```
   TWITTER_USERNAME=your_twitter_username_here
   TWITTER_PASSWORD=your_twitter_password_here
   ```

3. **Install required dependencies**:
   ```bash
   pip install python-dotenv playwright
   playwright install chromium
   ```

## Usage

### Option 1: Direct Login

To manually log in and store the session:

```bash
python twitter_login.py
```

If you want to force a fresh login (ignoring any existing session):

```bash
python twitter_login.py --force
```

### Option 2: Integrated Extraction

The login functionality is integrated into the main extraction scripts:

```bash
# Using the login-enhanced extraction script
python final_extract.py TwitterDev 20 5 5
```

Alternatively, use the test script to perform a full test:

```bash
./test_login_extraction.sh
```

## How It Works

1. The system first checks for a valid stored session (less than 24 hours old)
2. If no valid session exists, a new Playwright browser is launched
3. The script navigates to Twitter's login page and fills in credentials with human-like patterns
4. If successful, the session state is saved for future use
5. When extraction is needed, the stored session is loaded automatically
6. If authentication issues are detected, a fresh login is performed

## Handling CAPTCHAs and Verification

When Twitter presents a CAPTCHA or verification challenge:

1. The script detects the challenge
2. The browser remains open and pauses execution
3. You'll need to manually complete the verification
4. After manual verification, the script continues and saves the session

## Troubleshooting

- **Login Failures**: Check your credentials in the `.env` file
- **Permission Errors**: Ensure the script has write permissions in the directory
- **Browser Launch Issues**: Make sure Playwright is properly installed (`playwright install chromium`)
- **Session Not Persisting**: Check that the storage file is not being deleted by other processes

## Security Considerations

- Credentials are stored in the `.env` file which should be kept secure
- The browser session state is saved locally and contains authentication data
- Never commit `.env` or session state files to version control
- Consider using a dedicated Twitter account for scraping purposes 