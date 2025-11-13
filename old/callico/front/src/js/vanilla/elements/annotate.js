import { isEmpty, isEqual, xorWith } from 'lodash'
import { initFormset } from '../utils/formset.js'
import { dispatchUpdateProps, SELECT_ELEMENT_EVENT, UNSELECT_ELEMENT_EVENT, CREATE_ELEMENT_EVENT, UPDATE_ELEMENT_EVENT } from '../events/interactive_image.js'
import { displayElements } from './base.js'
import { DISPLAY_BUTTON_CLASS, DISPLAY_BUTTON_ATTRIBUTE, getElementTable, addRow, selectButton, unselectButton } from './table.js'
import { getTypeOption, initTypes, SELECTED_TYPE } from './types.js'
import { getUserTaskAnnotation, setUserTaskAnnotation, displayWarning } from '../annotations/storage.js'

const initElements = (userTaskID, parentID, elements) => {
  // Display elements of the previous version
  const table = getElementTable(document)
  displayElements(userTaskID, parentID, elements, true, table)
}

const initLibraryEvents = (userTaskID, parentID, elements) => {
  document.addEventListener(SELECT_ELEMENT_EVENT, (evt) => {
    const elementId = evt.detail
    const button = document.querySelector(`.${DISPLAY_BUTTON_CLASS}[${DISPLAY_BUTTON_ATTRIBUTE}="${elementId}"]`)
    if (button) selectButton(button)
  })

  document.addEventListener(UNSELECT_ELEMENT_EVENT, (evt) => {
    const elementId = evt.detail
    const button = document.querySelector(`.${DISPLAY_BUTTON_CLASS}[${DISPLAY_BUTTON_ATTRIBUTE}="${elementId}"]`)
    if (button) unselectButton(button)
  })

  document.addEventListener(CREATE_ELEMENT_EVENT, (evt) => {
    const element = evt.detail
    const localElement = {
      element_type: SELECTED_TYPE.id,
      polygon: element.polygon
    }
    elements[element.id - 1] = localElement
    setUserTaskAnnotation(userTaskID, parentID, elements)

    const table = getElementTable(document)
    addRow(userTaskID, parentID, element.id, SELECTED_TYPE.name, table, elements)
  })

  document.addEventListener(UPDATE_ELEMENT_EVENT, (evt) => {
    const { id, newPolygon } = evt.detail
    elements[id - 1] = { ...elements[id - 1], polygon: newPolygon }
    setUserTaskAnnotation(userTaskID, parentID, elements)
  })
}

const loadStoredElements = (userTaskID, parentID) => {
  const elements = getUserTaskAnnotation(userTaskID, parentID) || []

  for (const element of [...elements]) {
    if (!element) continue
    /*
     * Remove invalid elements to avoid form errors
     * This can happen if the configuration has changed
     */
    const typeOption = getTypeOption(element.element_type)
    if (!typeOption) {
      elements.splice(elements.indexOf(element), 1)
      continue
    }
  }

  return elements.length ? elements : null
}

export const bootElementsAnnotate = (userTaskID, parentID, previousElements) => {
  const elements = loadStoredElements(userTaskID, parentID) || previousElements
  if (!isEmpty(xorWith(elements.filter(child => child), previousElements, isEqual))) displayWarning(userTaskID, parentID)
  const children = elements.map((element, index) => (element ? { id: index + 1, ...element } : null))
  dispatchUpdateProps({ children })

  initElements(userTaskID, parentID, elements)
  initTypes()
  initFormset(elements, (key, value) => key === 'polygon' ? JSON.stringify(value) : value)
  initLibraryEvents(userTaskID, parentID, elements)
}
