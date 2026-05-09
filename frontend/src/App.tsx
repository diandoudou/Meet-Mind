/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import ProjectDetail from './pages/ProjectDetail';
import MeetingRoom from './pages/MeetingRoom';
import GlobalSearch from './pages/GlobalSearch';
import Tasks from './pages/Tasks';
import Layout from './components/Layout';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/projects" element={<Navigate to="/" replace />} />
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/project/:projectId" element={<ProjectDetail />} />
          <Route path="/meeting/:meetingId" element={<MeetingRoom />} />
          <Route path="/search" element={<GlobalSearch />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

