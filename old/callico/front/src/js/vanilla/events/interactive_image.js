export const dispatchDeleteElement = (id) => {
  document.dispatchEvent(new CustomEvent(DELETE_ELEMENT_EVENT, { detail: id }))
}

export const dispatchUpdateHighlightedElements = (ids) => {
  document.dispatchEvent(new CustomEvent(UPDATE_HIGHLIGHTED_ELEMENTS_EVENT, { detail: ids }))
}

export const dispatchUpdateSelectedElements = (ids) => {
  document.dispatchEvent(new CustomEvent(UPDATE_SELECTED_ELEMENTS_EVENT, { detail: ids }))
}

export const dispatchSelectElement = (id) => {
  document.dispatchEvent(new CustomEvent(SELECT_ELEMENT_EVENT, { detail: id }))
}

export const dispatchUnselectElement = (id) => {
  document.dispatchEvent(new CustomEvent(UNSELECT_ELEMENT_EVENT, { detail: id }))
}

export const dispatchUpdateProps = (props) => {
  document.dispatchEvent(new CustomEvent(UPDATE_PROPS, { detail: props }))
}

export const CREATE_ELEMENT_EVENT = 'create-element'
export const DELETE_ELEMENT_EVENT = 'delete-element'
export const UPDATE_PROPS = 'update-props'
export const UPDATE_ELEMENT_EVENT = 'update-element'
export const UPDATE_HIGHLIGHTED_ELEMENTS_EVENT = 'update-highlighted-elements'
export const UPDATE_SELECTED_ELEMENTS_EVENT = 'update-selected-elements'
export const SELECT_ELEMENT_EVENT = 'select-element'
export const UNSELECT_ELEMENT_EVENT = 'unselect-element'
