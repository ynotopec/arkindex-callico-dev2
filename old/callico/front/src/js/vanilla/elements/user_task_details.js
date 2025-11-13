import { dispatchUpdateProps, dispatchUpdateSelectedElements, SELECT_ELEMENT_EVENT, UNSELECT_ELEMENT_EVENT } from '../events/interactive_image.js'
import { displayElements } from './base.js'
import { DISPLAY_BUTTON_ATTRIBUTE, DISPLAY_BUTTON_CLASS, BUTTON_SELECTED_CLASS, getElementTable, getEmptyRow, selectButton, unselectButton } from './table.js'

const DIV_ATTRIBUTE = 'answer-elements'

const unselectAllButtons = () => {
  document.querySelectorAll(`.${DISPLAY_BUTTON_CLASS}`).forEach(btn => {
    unselectButton(btn)
  })
}

const displayVersion = (button) => {
  const div = button.parentElement
  const newVersion = div.getAttribute(DIV_ATTRIBUTE)
  const elements = JSON.parse(newVersion)
  const table = getElementTable(div)

  // Before displaying another version we need to reset the selected element just in case
  dispatchUpdateSelectedElements([])
  unselectAllButtons()

  // Empty the table
  const emptyRow = getEmptyRow(table)
  emptyRow.classList.remove('is-hidden')
  table.querySelectorAll('tbody tr').forEach(row => {
    if (row === emptyRow) return
    row.parentElement.removeChild(row)
  })

  displayElements(null, null, elements, false, table)
  dispatchUpdateProps({ children: elements })

  document.querySelectorAll(`.${DISPLAY_BUTTON_CLASS}`).forEach(btn => {
    const answer = btn.closest(`div[${DIV_ATTRIBUTE}]`)
    if (answer.getAttribute(DIV_ATTRIBUTE) === newVersion) return
    // Removing the display button since the displayed version isn't in its ancestors
    btn.parentElement.removeChild(btn)
  })
}

const initButtons = () => {
  document.querySelectorAll(`div[${DIV_ATTRIBUTE}]`).forEach(div => {
    const button = div.querySelector('button')
    button.addEventListener('click', () => {
      displayVersion(button)
    })
  })
}

const initElements = () => {
  // Display a table for each version
  document.querySelectorAll('.dropdown-toggle-content button').forEach(button => {
    displayVersion(button)
  })

  // Display the last annotation by default
  const button = document.querySelector('.dropdown-toggle-content:not(.is-hidden) button')
  if (!button) return
  button.click()
}

const getButton = (elementId) => {
  // Select the first open version
  let button = document.querySelector(`.dropdown-toggle-content:not(.is-hidden) .${DISPLAY_BUTTON_CLASS}[${DISPLAY_BUTTON_ATTRIBUTE}="${elementId}"]`)

  if (!button) {
    // Select the first version
    button = document.querySelector(`.dropdown-toggle-content .${DISPLAY_BUTTON_CLASS}[${DISPLAY_BUTTON_ATTRIBUTE}="${elementId}"]`)
    if (!button) return
    // Simulate a click to open the dropdown
    const dropdown = button.closest('.dropdown-toggle').querySelector('.dropdown-toggle-title')
    dropdown.click()
  }

  return button
}

const initLibraryEvents = () => {
  document.addEventListener(SELECT_ELEMENT_EVENT, (evt) => {
    const elementId = evt.detail

    // Check if a button is already selected
    const selectedButton = document.querySelector(`.dropdown-toggle-content .${DISPLAY_BUTTON_CLASS}.${BUTTON_SELECTED_CLASS}[${DISPLAY_BUTTON_ATTRIBUTE}="${elementId}"]`)
    if (selectedButton) return

    unselectAllButtons()
    dispatchUpdateSelectedElements([elementId])

    // Focus on the button next to the answer
    const buttonToSelect = getButton(elementId)
    if (!buttonToSelect) return
    selectButton(buttonToSelect)
    buttonToSelect.scrollIntoView({ block: 'center', inline: 'center' })
  })

  document.addEventListener(UNSELECT_ELEMENT_EVENT, (evt) => {
    const elementId = evt.detail

    // Check if a button is already unselected
    const selectedButton = document.querySelector(`.dropdown-toggle-content .${DISPLAY_BUTTON_CLASS}.${BUTTON_SELECTED_CLASS}[${DISPLAY_BUTTON_ATTRIBUTE}="${elementId}"]`)
    if (!selectedButton) return

    unselectAllButtons()

    // Focus on the button next to the answer
    const buttonToUnselect = getButton(elementId)
    if (!buttonToUnselect) return
    unselectButton(buttonToUnselect)
    buttonToUnselect.scrollIntoView({ block: 'center', inline: 'center' })
  })
}

export const bootElementsUserTaskDetails = () => {
  initButtons()
  initElements()
  initLibraryEvents()
}
