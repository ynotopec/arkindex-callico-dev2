export const bootCompletionTime = () => {
  const startDate = new Date()

  // Look for a form field receiving the task completion time or fail silently
  const timeField = document.getElementById('completion_time')
  if (timeField === null) return

  const form = timeField.closest('form[method="post"]')
  if (form === null) return

  form.addEventListener('submit', () => {
    timeField.value = new Date() - startDate
  })
}
