<script setup>
</script>

<template>
  <header class="navbar">
    <div class="container">
      <router-link to="/" class="logo">Logo</router-link>
      <nav class="nav-links">
        <a href="#features">Features</a>
        <a href="#about">About</a>
        <a href="#contact">Contact</a>
      </nav>
      <button class="menu-toggle" aria-label="Toggle menu">
        <span></span><span></span><span></span>
      </button>
    </div>
  </header>

  <main>
    <section class="hero">
      <div class="container">
        <h1>Build Something Great</h1>
        <p>A clean, modern starting point for your next project.</p>
        <div class="hero-actions">
          <a href="#" class="btn btn-primary">Get Started</a>
          <a href="#" class="btn btn-outline">Learn More</a>
        </div>
      </div>
    </section>

    <section id="features" class="features">
      <div class="container">
        <h2>Features</h2>
        <div class="feature-grid">
          <div class="card">
            <div class="card-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/></svg>
            </div>
            <h3>Fast</h3>
            <p>Built with performance in mind.</p>
          </div>
          <div class="card">
            <div class="card-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/></svg>
            </div>
            <h3>Responsive</h3>
            <p>Looks great on every device.</p>
          </div>
          <div class="card">
            <div class="card-icon">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/></svg>
            </div>
            <h3>Simple</h3>
            <p>Clean code, easy to customize.</p>
          </div>
        </div>
      </div>
    </section>
  </main>

  <footer>
    <div class="container">
      <p>&copy; 2026 My Website. All rights reserved.</p>
    </div>
  </footer>
</template>

<style scoped>
/* scoped styles are minimal — shared styles in main.css */
</style>
