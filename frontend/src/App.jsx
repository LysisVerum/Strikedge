import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import LandingPage             from './pages/LandingPage';
import Dashboard               from './pages/Dashboard';
import LoginPage               from './pages/LoginPage';
import VerifyPage              from './pages/VerifyPage';
import AccountPage             from './pages/AccountPage';
import PrivacyPage             from './pages/PrivacyPage';
import TermsPage               from './pages/TermsPage';
import ResponsibleGamblingPage from './pages/ResponsibleGamblingPage';
import ContactPage             from './pages/ContactPage';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/"                     element={<LandingPage />}             />
          <Route path="/login"                element={<LoginPage />}               />
          <Route path="/verify"               element={<VerifyPage />}              />
          <Route path="/dashboard"            element={<Dashboard />}               />
          <Route path="/account"              element={<AccountPage />}             />
          <Route path="/privacy"              element={<PrivacyPage />}             />
          <Route path="/terms"                element={<TermsPage />}               />
          <Route path="/responsible-gambling" element={<ResponsibleGamblingPage />} />
          <Route path="/contact"              element={<ContactPage />}             />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
