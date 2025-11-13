import { addRow } from './table.js'
import { getTypeOption } from './types.js'

export const displayElements = (userTaskID, parentID, elements, removeElement, table) => {
  elements.forEach((element, index) => {
    if (!element) return
    const typeOption = getTypeOption(element.element_type)
    const typeName = typeOption ? typeOption.textContent : `Unknown type (${element.element_type})`
    addRow(userTaskID, parentID, index + 1, typeName, table, removeElement ? elements : null)
  })
}
