// Mobile menu toggle
const menuToggle = document.querySelector('.menu-toggle')
const navLinks = document.querySelector('.nav-links')

if (menuToggle && navLinks) {
  menuToggle.addEventListener('click', () => {
    navLinks.classList.toggle('open')
  })
}

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', (e) => {
    e.preventDefault()
    const target = document.querySelector(anchor.getAttribute('href'))
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  })
})
