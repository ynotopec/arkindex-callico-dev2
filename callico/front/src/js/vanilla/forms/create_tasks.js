const CREATE_TASKS_FORM_ID = 'create-tasks-form'

const initButtons = () => {
  const CREATE_TASKS_FORM = document.getElementById(CREATE_TASKS_FORM_ID)

  document.getElementById('preview-button').addEventListener('click', () => { CREATE_TASKS_FORM.target = '_blank' })
  document.getElementById('create-tasks-button').addEventListener('click', () => { CREATE_TASKS_FORM.target = '_self' })
}

export const bootCreateTasksForm = () => {
  initButtons()

  // Truncate really long user options
  document.querySelectorAll(`#${CREATE_TASKS_FORM_ID} label.radio`).forEach(option => {
    option.classList.add('truncate-long-words')
    option.setAttribute('title', option.textContent)
  })
}
