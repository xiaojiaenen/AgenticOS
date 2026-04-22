import React, { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { Home } from './pages/Home';
import { Chat } from './pages/Chat';
import { Login } from './pages/Login';
import { Signup } from './pages/Signup';

// Only keep rarely used, heavy admin dashboard as lazy
const AdminDashboard = lazy(() => import('./pages/AdminDashboard').then(m => ({ default: m.AdminDashboard })));

const LoadingPage = () => (
  <div className="h-screen w-full flex items-center justify-center bg-zinc-50">
    <motion.div 
      animate={{ rotate: 360 }}
      transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
      className="w-8 h-8 border-4 border-sky-500 border-t-transparent rounded-full"
    />
  </div>
);

// Wrapper to handle AnimatePresence for route transitions
const AnimatedRoutes = () => {
  const location = useLocation();
  
  return (
    <Suspense fallback={<LoadingPage />}>
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<Home />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/admin" element={<AdminDashboard />} />
        </Routes>
      </AnimatePresence>
    </Suspense>
  );
};

function App() {
  return (
    <Router>
      <AnimatedRoutes />
    </Router>
  );
}

export default App;
