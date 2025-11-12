export const dispatchCarouselTriggerSelection = (id) => {
  document.dispatchEvent(new CustomEvent(CAROUSEL_TRIGGER_SELECTION, { detail: id }))
}

export const CAROUSEL_SELECT_ELEMENT_EVENT = 'carousel-select-element'
export const CAROUSEL_TRIGGER_SELECTION = 'carousel-trigger-selection'
