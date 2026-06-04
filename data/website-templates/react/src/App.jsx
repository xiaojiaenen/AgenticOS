import React from 'react'
import { Routes, Route, Link } from 'react-router-dom'
import Home from './pages/Home'

export default function App() {
  return (
    <>
      <header className="navbar">
        <div className="container">
          <Link to="/" className="logo">Logo</Link>
          <nav className="nav-links">
            <a href="#features">Features</a>
            <a href="#about">About</a>
            <a href="#contact">Contact</a>
          </nav>
          <button className="menu-toggle" aria-label="Toggle menu">
            <span></span><span></span><span></span>
          </button>
        </div>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Home />} />
        </Routes>
      </main>

      <footer>
        <div className="container">
          <p>&copy; 2026 My Website. All rights reserved.</p>
        </div>
      </footer>
    </>
  )
}
