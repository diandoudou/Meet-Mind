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
