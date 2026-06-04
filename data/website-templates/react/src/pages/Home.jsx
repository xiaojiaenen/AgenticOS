export default function Home() {
  return (
    <>
      <section className="hero">
        <div className="container">
          <h1>Build Something Great</h1>
          <p>A clean, modern starting point for your next project.</p>
          <div className="hero-actions">
            <a href="#" className="btn btn-primary">Get Started</a>
            <a href="#" className="btn btn-outline">Learn More</a>
          </div>
        </div>
      </section>

      <section id="features" className="features">
        <div className="container">
          <h2>Features</h2>
          <div className="feature-grid">
            <div className="card">
              <div className="card-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/></svg>
              </div>
              <h3>Fast</h3>
              <p>Built with performance in mind.</p>
            </div>
            <div className="card">
              <div className="card-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="2" y="3" width="20" height="14" rx="2"/></svg>
              </div>
              <h3>Responsive</h3>
              <p>Looks great on every device.</p>
            </div>
            <div className="card">
              <div className="card-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/></svg>
              </div>
              <h3>Simple</h3>
              <p>Clean code, easy to customize.</p>
            </div>
          </div>
        </div>
      </section>
    </>
  )
}
