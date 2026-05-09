<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# MeetMind - AI-Powered Meeting Assistant

Real-time meeting transcription and intelligent analysis powered by AI.

## Features

- 🎙️ Real-time speech recognition
- 📝 Automatic meeting transcription
- 🤖 AI-powered meeting summaries
- ✅ Smart action item extraction
- 📊 Project-based organization
- 🔍 Global search across meetings
- 📄 PDF document upload and analysis

## Run Locally

**Prerequisites:** Node.js 18+

### 1. Clone the repository
```bash
git clone https://github.com/diandoudou/Meet-Mind.git
cd Meet-Mind
```

### 2. Install dependencies
```bash
npm install
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Required environment variables:

#### Firebase Configuration
Get these from [Firebase Console](https://console.firebase.google.com/) > Project Settings > General:

```env
VITE_FIREBASE_PROJECT_ID="your-project-id"
VITE_FIREBASE_APP_ID="1:123456789:web:abcdef123456"
VITE_FIREBASE_API_KEY="your-firebase-api-key"
VITE_FIREBASE_AUTH_DOMAIN="your-project.firebaseapp.com"
VITE_FIREBASE_FIRESTORE_DATABASE_ID="your-database-id"
VITE_FIREBASE_STORAGE_BUCKET="your-project.firebasestorage.app"
VITE_FIREBASE_MESSAGING_SENDER_ID="123456789"
VITE_FIREBASE_MEASUREMENT_ID=""
```

#### Gemini AI API
Get your API key from [Google AI Studio](https://makersuite.google.com/app/apikey):

```env
GEMINI_API_KEY="your-gemini-api-key"
```

### 4. Run the development server
```bash
npm run dev
```

The app will be available at `http://localhost:5173`

## Backend Setup

The real-time transcription backend is in the `MeetingAssistant` folder. See its README for setup instructions.

## Security Note

⚠️ **Never commit API keys or sensitive credentials to the repository!**

- All sensitive data should be in `.env` (which is gitignored)
- Use `.env.example` as a template only
- Firebase configuration files are excluded from git

## Tech Stack

- **Frontend:** React 19, TypeScript, Vite
- **UI:** TailwindCSS, Motion (Framer Motion), Lucide Icons
- **Backend:** Python, FastAPI, WebSocket
- **Database:** Firebase Firestore, Firebase Storage
- **AI:** Google Gemini 2.5 Flash, DashScope ASR

## License

MIT
