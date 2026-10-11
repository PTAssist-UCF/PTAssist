import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import PatientPage from './pages/patient/PatientPage';
import TherapistPage from './pages/therapist/TherapistPage';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/patient" replace />} />
        <Route path="/patient" element={<PatientPage />} />
        <Route path="/therapist" element={<TherapistPage />} />
        <Route path="*" element={<Navigate to="/patient" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
