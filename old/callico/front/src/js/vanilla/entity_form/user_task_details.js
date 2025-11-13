import { bootFieldGroups } from './base'

export const bootEntityFormUserTaskDetails = () => {
  const containers = document.querySelectorAll('.dropdown-toggle-content')

  containers.forEach(container => {
    bootFieldGroups(container, '.answer-field', 'mb-5')
  })
}
