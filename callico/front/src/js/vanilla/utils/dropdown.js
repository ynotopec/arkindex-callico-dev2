const _toggleDropdown = (div) => {
  div.querySelector('.icon').classList.toggle('active')
  div.parentElement.querySelector('.dropdown-toggle-content').classList.toggle('is-hidden')
}

export const bootDropdowns = () => {
  document.querySelectorAll('.dropdown-toggle-title').forEach(div => {
    div.addEventListener('click', () => { _toggleDropdown(div) })
  })
}
