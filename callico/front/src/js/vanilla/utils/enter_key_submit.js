export const confirmEnterKeySubmit = (form, confirmContent) => {
  form.addEventListener('keydown', (event) => {
    // If the Enter key was pressed, we want confirmation before submitting the form
    if (event.key === 'Enter' && !event.srcElement.classList.contains('ignore-confirm')) {
      const response = confirm(confirmContent)
      if (!response) event.preventDefault()
    }
  })
}
