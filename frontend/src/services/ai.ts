import { GoogleGenAI } from "@google/genai";
import { TranscriptEntry, ActionItem } from "../types";

const GEMINI_API_KEY = import.meta.env.VITE_GEMINI_API_KEY;
const ai = GEMINI_API_KEY ? new GoogleGenAI({ apiKey: GEMINI_API_KEY }) : null;

const SYSTEM_INSTRUCTION = `
You are MeetMind, a specialized Academic Meeting Assistant and student 'Second Brain'. 
Your goal is to help students and researchers manage their project-centric collaboration.
You support bilingual (Chinglish) transcription, terminology correction, and automated task management.
Always be precise, academic, and encouraging.
`;

export async function summarizeMeeting(transcript: TranscriptEntry[]): Promise<string> {
  if (!ai) {
    return "Gemini API key is not configured. Please set VITE_GEMINI_API_KEY in frontend/.env.";
  }

  const text = transcript.map(t => `[${t.speaker}]: ${t.text}`).join('\n');
  const response = await ai.models.generateContent({
    model: "gemini-3-flash-preview",
    contents: `Please provide a concise academic summary of this meeting transcript:\n\n${text}`,
    config: { systemInstruction: SYSTEM_INSTRUCTION }
  });
  return response.text || "Summary generation failed.";
}

export async function extractActionItems(transcript: TranscriptEntry[], projectId: string, meetingId: string): Promise<ActionItem[]> {
  if (!ai) {
    console.warn("Gemini API key is not configured. Skipping AI action-item extraction.");
    return [];
  }

  const text = transcript.map(t => `[${t.speaker}]: ${t.text}`).join('\n');
  const response = await ai.models.generateContent({
    model: "gemini-3-flash-preview",
    contents: `Extract action items from this meeting transcription in JSON format.
    Return an array of objects with fields: task, assignee, deadline (approximate date string).
    Transcription:\n\n${text}`,
    config: { 
      systemInstruction: SYSTEM_INSTRUCTION,
      responseMimeType: "application/json"
    }
  });

  try {
    const data = JSON.parse(response.text || "[]");
    return data.map((d: any, i: number) => ({
      id: `ai-${Date.now()}-${i}`,
      projectId,
      meetingId,
      task: d.task,
      assignee: d.assignee,
      deadline: d.deadline ? new Date(d.deadline).getTime() : Date.now() + 86400000 * 7,
      status: 'pending'
    }));
  } catch (e) {
    console.error("Failed to parse action items", e);
    return [];
  }
}

export async function suggestAgenda(projectContext: string, previousMeetingSummary?: string): Promise<string> {
  if (!ai) {
    return "Gemini API key is not configured. Please set VITE_GEMINI_API_KEY in frontend/.env.";
  }

  const response = await ai.models.generateContent({
    model: "gemini-3-flash-preview",
    contents: `Based on the project context: "${projectContext}" and the previous meeting summary: "${previousMeetingSummary || 'None'}", suggest a concise academic agenda for the next meeting.`,
    config: { systemInstruction: SYSTEM_INSTRUCTION }
  });
  return response.text || "Agenda suggestions currently unavailable.";
}

const API_URL = import.meta.env.VITE_API_URL || import.meta.env.VITE_BACKEND_URL || 'http://localhost:8765';

export interface StructuredSummary {
  title: string;
  date?: string;
  participants: string[];
  topics: Array<{
    title: string;
    discussion_points: string[];
    participants?: string[];
    conclusion?: string;
  }>;
  decisions: string[];
  next_steps: string[];
  overview?: string;
}

export interface BackendActionItem {
  id: string;
  projectId: string;
  meetingId: string;
  task: string;
  assignee: string;
  deadline: number;
  priority?: string;
  context?: string;
  status: 'pending' | 'completed' | 'overdue';
}

export interface RagCitation {
  label: string;
  chunk_id: string;
  source_type: 'meeting_transcript' | 'meeting_summary' | 'pdf' | 'action_item';
  source_id: string;
  source_title: string;
  excerpt: string;
  url_path?: string;
}

export interface RagSearchResult {
  chunk_id: string;
  score: number;
  text: string;
  source_type: string;
  source_id: string;
  source_title: string;
  project_id: string;
  project_name?: string;
  speaker?: string;
  timestamp?: number;
  citation_label?: string;
}

export interface StopMeetingResponse {
  status: string;
  summary: string;
  summary_structured?: StructuredSummary | null;
  action_items: BackendActionItem[];
  transcript: Array<{
    speaker: string;
    text: string;
    timestamp: string;
    language: string;
  }>;
  errors?: string[];
}

export interface RagChatResponse {
  answer: string;
  citations: RagCitation[];
  retrieval_meta?: {
    chunks_used?: number;
    latency_ms?: number;
  };
}

export async function stopMeetingRecording(params: {
  projectId?: string;
  meetingId?: string;
  ownerUid?: string;
  meetingTitle?: string;
}): Promise<StopMeetingResponse> {
  const response = await fetch(`${API_URL}/stop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      project_id: params.projectId || '',
      meeting_id: params.meetingId || '',
      owner_uid: params.ownerUid || '',
      meeting_title: params.meetingTitle || '',
    }),
  });

  if (!response.ok) {
    throw new Error(`Stop meeting failed: ${response.status}`);
  }

  return response.json();
}

export async function searchKnowledge(params: {
  query: string;
  ownerUid: string;
  projectId?: string;
  projectName?: string;
  topK?: number;
}): Promise<RagSearchResult[]> {
  const response = await fetch(`${API_URL}/api/rag/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: params.query,
      owner_uid: params.ownerUid,
      project_id: params.projectId || null,
      project_name: params.projectName || '',
      top_k: params.topK || 10,
    }),
  });

  if (!response.ok) {
    throw new Error(`RAG search failed: ${response.status}`);
  }

  const data = await response.json();
  return data.results || [];
}

export async function ragChat(params: {
  message: string;
  ownerUid: string;
  projectId?: string;
  projectName?: string;
  topK?: number;
}): Promise<RagChatResponse> {
  const response = await fetch(`${API_URL}/api/rag/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: params.message,
      owner_uid: params.ownerUid,
      project_id: params.projectId || '',
      project_name: params.projectName || '',
      top_k: params.topK || 6,
    }),
  });

  if (!response.ok) {
    throw new Error(`RAG chat failed: ${response.status}`);
  }

  return response.json();
}

export async function indexPdfFile(params: {
  file: File;
  ownerUid: string;
  projectId: string;
  fileId: string;
  fileTitle: string;
}): Promise<{ indexed_chunks: number }> {
  const form = new FormData();
  form.append('file', params.file);
  form.append('owner_uid', params.ownerUid);
  form.append('project_id', params.projectId);
  form.append('file_id', params.fileId);
  form.append('file_title', params.fileTitle);

  const response = await fetch(`${API_URL}/api/rag/index/pdf-file`, {
    method: 'POST',
    body: form,
  });

  if (!response.ok) {
    throw new Error(`PDF index failed: ${response.status}`);
  }

  return response.json();
}

export async function chatWithAssistant(message: string, context = ''): Promise<string> {
  const response = await fetch(`${API_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context }),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  const data = await response.json();
  return data.reply || 'No response from assistant.';
}
