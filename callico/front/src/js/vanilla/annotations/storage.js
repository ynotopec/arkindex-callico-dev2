const SUBMITTED_USER_TASK = 'callico-submitted-user-task'

const storageKey = (userTaskID, parentID) => {
  return `callico-user-task-${userTaskID}-${parentID}`
}

const removeUserTaskAnnotationStorage = (userTaskID, parentID) => {
  const key = storageKey(userTaskID, parentID)
  localStorage.removeItem(key)
}

export const getUserTaskAnnotation = (userTaskID, parentID) => {
  const key = storageKey(userTaskID, parentID)
  return JSON.parse(localStorage.getItem(key))
}

export const setUserTaskAnnotation = (userTaskID, parentID, value) => {
  const key = storageKey(userTaskID, parentID)
  localStorage.setItem(key, JSON.stringify(value))
}

export const bootUserTaskAnnotationStorage = (userTaskID, parentID) => {
  // Save the user task ID that will be sent
  const form = document.querySelector('.annotation-form')
  if (!form) return
  form.addEventListener('submit', () => {
    const value = JSON.stringify({ id: userTaskID, parent: parentID })
    localStorage.setItem(SUBMITTED_USER_TASK, value)
  })
}

export const cleanUserTaskAnnotationStorage = (userTaskID = null) => {
  // Delete the previously sent annotation to save space
  const submittedUserTask = JSON.parse(localStorage.getItem(SUBMITTED_USER_TASK))
  /*
   * Do not delete the previous annotation if it is from the current user task
   * This can happen if the form was invalid
   */
  if (submittedUserTask && (!userTaskID || userTaskID !== submittedUserTask.id)) {
    removeUserTaskAnnotationStorage(submittedUserTask.id, submittedUserTask.parent)
  }
  /*
   * Always delete the previous user task as the form could have been invalid
   * Reusing this function from a different page should not delete the annotation
   */
  localStorage.removeItem(SUBMITTED_USER_TASK)
}

export const displayWarning = (userTaskID, parentID) => {
  const notification = document.querySelector('.notification.is-warning')
  notification.classList.remove('is-hidden')

  const a = notification.querySelector('a')
  a.addEventListener('click', () => {
    removeUserTaskAnnotationStorage(userTaskID, parentID)
  })
}
