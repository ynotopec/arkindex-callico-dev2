import { CAROUSEL_SELECT_ELEMENT_EVENT } from '../events/carousel.js'
import { dispatchUpdateProps } from '../events/interactive_image.js'

export const initCarouselLibraryEvents = () => {
  document.addEventListener(CAROUSEL_SELECT_ELEMENT_EVENT, (evt) => {
    const element = evt.detail
    dispatchUpdateProps({ element, children: element.children })
  })
}
