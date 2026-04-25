import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import LandingPage from './pages/LandingPage';
import Dashboard   from './pages/Dashboard';
import LoginPage   from './pages/LoginPage';
import VerifyPage  from './pages/VerifyPage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/"          element={<LandingPage />} />
          <Route path="/login"     element={<LoginPage />}   />
          <Route path="/verify"    element={<VerifyPage />}  />
          <Route path="/dashboard" element={<Dashboard />}   />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
