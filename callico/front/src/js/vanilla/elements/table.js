import { dispatchDeleteElement, dispatchUpdateSelectedElements, dispatchUnselectElement } from '../events/interactive_image.js'
import { setUserTaskAnnotation } from '../annotations/storage.js'

const ELEMENT_TABLE_CLASS = 'element-table'
const EMPTY_ROW_CLASS = 'empty-row'

const TR_SELECTED_CLASS = 'has-background-grey-lighter'

const _displayHideElement = (button, elementId) => {
  if (button.classList.contains(BUTTON_SELECTED_CLASS)) {
    unselectButton(button)
    dispatchUnselectElement(elementId)
  } else {
    // Only select one element at once
    document.querySelectorAll(`.${DISPLAY_BUTTON_CLASS}`).forEach(btn => {
      unselectButton(btn)
    })
    selectButton(button)
    dispatchUpdateSelectedElements([elementId])
  }
}

const _deleteElement = (userTaskID, parentID, elements, elementId, row) => {
  // Only nullify the object to keep the synchronization between ID and list index
  elements[elementId - 1] = null
  setUserTaskAnnotation(userTaskID, parentID, elements)

  // Update rows of the table
  const tbody = row.parentElement
  tbody.removeChild(row)
  if (!elements.length || elements.every(element => !element)) {
    const emptyRow = getEmptyRow(tbody)
    emptyRow.classList.remove('is-hidden')
  }

  dispatchDeleteElement(elementId)
}

export const selectButton = (button) => {
  button.classList.add(BUTTON_SELECTED_CLASS)
  button.firstChild.classList.remove('fa-eye')
  button.firstChild.classList.add('fa-eye-slash')

  const tr = button.closest('tr')
  tr.classList.add(TR_SELECTED_CLASS)
}

export const unselectButton = (button) => {
  button.classList.remove(BUTTON_SELECTED_CLASS)
  button.firstChild.classList.remove('fa-eye-slash')
  button.firstChild.classList.add('fa-eye')

  const tr = button.closest('tr')
  tr.classList.remove(TR_SELECTED_CLASS)
}

export const getElementTable = (element) => {
  return element.querySelector(`table.${ELEMENT_TABLE_CLASS}`)
}

export const getEmptyRow = (element) => {
  return element.querySelector(`tr.${EMPTY_ROW_CLASS}`)
}

export const addRow = (userTaskID, parentID, elementId, typeName, table, elements) => {
  const row = table.insertRow()

  // Cell to display the type of the element
  const typeCell = row.insertCell()
  typeCell.classList.add('truncate-long-words', 'restricted-max-width-100')
  typeCell.setAttribute('title', typeName)
  typeCell.appendChild(document.createTextNode(typeName))

  // Display/Hide button
  const displayHideIcon = document.createElement('i')
  displayHideIcon.classList.add('fas', 'fa-eye')

  const displayHideButton = document.createElement('span')
  displayHideButton.setAttribute(DISPLAY_BUTTON_ATTRIBUTE, elementId)
  displayHideButton.classList.add('icon', 'is-clickable', 'mr-5', DISPLAY_BUTTON_CLASS)
  displayHideButton.addEventListener('click', () => { _displayHideElement(displayHideButton, elementId) })
  displayHideButton.appendChild(displayHideIcon)

  // Adding the button to the row
  const buttonsDiv = document.createElement('div')
  buttonsDiv.appendChild(displayHideButton)

  if (elements) {
    // Delete button
    const deleteIcon = document.createElement('i')
    deleteIcon.classList.add('fas', 'fa-trash')

    const deleteButton = document.createElement('span')
    deleteButton.classList.add('icon', 'is-clickable', 'has-text-danger')
    deleteButton.addEventListener('click', () => _deleteElement(userTaskID, parentID, elements, elementId, row))
    deleteButton.appendChild(deleteIcon)

    // Adding the button to the row
    buttonsDiv.classList.add('is-flex')
    buttonsDiv.appendChild(deleteButton)
  }

  // Cell to display the display/hide and delete buttons
  const buttonsCell = row.insertCell()
  buttonsCell.appendChild(buttonsDiv)

  // Update rows of the table
  const emptyRow = getEmptyRow(table)
  emptyRow.classList.add('is-hidden')
}

export const DISPLAY_BUTTON_ATTRIBUTE = 'element-id'
export const DISPLAY_BUTTON_CLASS = 'display-hide-button'
export const BUTTON_SELECTED_CLASS = 'selected'
