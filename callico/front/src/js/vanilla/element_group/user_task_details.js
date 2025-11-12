import { uniq } from 'lodash'
import { dispatchUpdateHighlightedElements, dispatchUpdateSelectedElements } from '../events/interactive_image.js'

const DIV_ATTRIBUTE = 'answer-groups'

const hideAllElementGroupManagers = () => {
  document.querySelectorAll(`div[${DIV_ATTRIBUTE}] > div:not(.is-hidden)`).forEach(elementGroupManager => {
    elementGroupManager.classList.add('is-hidden')
  })
}

const displayVersion = (button) => {
  const div = button.parentElement
  const newVersion = div.getAttribute(DIV_ATTRIBUTE)
  const groups = JSON.parse(newVersion)

  // Only display the ElementGroupManager of the current version
  hideAllElementGroupManagers()
  const elementGroupManager = div.children[div.children.length - 1]
  elementGroupManager.classList.remove('is-hidden')

  // Reset the selected/highlighted elements on InteractiveImage
  dispatchUpdateSelectedElements(uniq(Object.values(groups).map(group => group.elements).flat()))
  dispatchUpdateHighlightedElements([])
}

const initButtons = () => {
  document.querySelectorAll(`div[${DIV_ATTRIBUTE}]`).forEach(div => {
    const button = div.querySelector('button')
    button.addEventListener('click', () => {
      displayVersion(button)
    })
  })
}

const initGroups = () => {
  // Display the last annotation by default
  const button = document.querySelector('.dropdown-toggle-content:not(.is-hidden) button')
  if (!button) return
  button.click()
}

export const bootElementGroupUserTaskDetails = () => {
  initButtons()
  initGroups()
}
