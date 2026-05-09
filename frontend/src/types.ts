export interface Project {
  id: string;
  name: string;
  description: string;
  color: string;
  ownerUid: string;
  members: string[];
  createdAt: number;
}

export interface Meeting {
  id: string;
  projectId: string;
  title: string;
  date: number;
  summary?: string;
  transcript?: TranscriptEntry[];
}

export interface TranscriptEntry {
  speaker: string;
  text: string;
  timestamp: number;
  language: 'zh' | 'en' | 'mixed';
  isCommand?: boolean;
  isSystem?: boolean;
  translation?: string;
  isTranslating?: boolean;
}

export interface ActionItem {
  id: string;
  projectId: string;
  meetingId: string;
  task: string;
  assignee: string;
  deadline: number;
  status: 'pending' | 'completed' | 'overdue';
}

export interface ProjectFile {
  id: string;
  name: string;
  size: number;
  type: string;
  storagePath: string;
  downloadURL: string;
  uploadedAt: number;
  uploadedBy: string;
}
