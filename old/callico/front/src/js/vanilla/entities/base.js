import { getColor } from './labels.js'
import { setUserTaskAnnotation } from '../annotations/storage.js'

const hasRealSibling = (sibling) => {
  return sibling && !(sibling.nodeName === '#text' || sibling.classList.contains('delete'))
}

export const createTag = (range, label) => {
  // Create tag
  const tag = document.createElement('div')
  tag.classList.add('tag', 'is-medium', 'px-1', 'py-0')
  tag.style.backgroundColor = getColor(label)

  /*
   * Add a title so that the manager can see the entities whose type is not in the configuration
   * This can happen if the configuration has changed
   */
  if (label) tag.setAttribute('title', label)

  /*
   * Try to find a common ancestor to simplify and surround the selected range.
   *
   * This is useful in special cases like:
   *
   *                   ⚲ (start <desc>)                       ⚲ (end </desc>)
   *  <name><first−name>Jane</first−name> Doe</name> is a woman
   *
   * In the above example, we selected the text "Jane Doe is a woman", a valid nested entity.
   * The starting point is located in the entity `first−name` (child of `name`), the ending one is in the text.
   * Trying to surround with those locations WILL NOT WORK.
   *
   * Therefore, we try to find a common ancestor for both positions (start and end) without altering the amount
   * of selected text. Here, we will end up with:
   *
   * ⚲ (start <desc>)                                         ⚲ (end </desc>)
   *  <name><first−name>Jane</first−name> Doe</name> is a woman
   *
   * The final selection will successfully surround both `name` and `first−name` entities,
   * allowing us to create an entity containing the "Jane Doe is a woman" text.
   */
  if (range.startContainer.parentNode !== range.endContainer.parentNode) {
    if (range.startOffset === 0) {
      while (range.startContainer !== range.commonAncestorContainer && !hasRealSibling(range.startContainer.previousSibling)) {
        range.setStartBefore(range.startContainer)
      }
    }

    if (range.endOffset === range.endContainer.length) {
      while (range.endContainer !== range.commonAncestorContainer && !hasRealSibling(range.endContainer.nextSibling)) {
        range.setEndAfter(range.endContainer)
      }
    }
  }

  // Surround the selected text with the created tag
  range.surroundContents(tag)

  return tag
}

export const addDeleteButton = (userTaskID, parentID, entities, tag, entity, removeEntityFunction) => {
  const button = document.createElement('button')
  button.classList.add('delete', 'is-small', 'ml-1', 'mr-0')
  button.style.verticalAlign = 'text-bottom'
  button.setAttribute('type', 'button')
  button.addEventListener('click', () => {
    removeEntityFunction(entities, tag, entity)
    setUserTaskAnnotation(userTaskID, parentID, entities)
  })
  tag.appendChild(button)
}

const _findEntityEdgeNode = (node, expectedOffset, currentOffset) => {
  if (node.nodeName === '#text') {
    if (currentOffset + node.textContent.length > expectedOffset) {
      return { node, offsetInNode: expectedOffset - currentOffset, updatedOffset: currentOffset }
    }

    currentOffset += node.textContent.length
  }

  for (const child of node.childNodes) {
    const result = _findEntityEdgeNode(child, expectedOffset, currentOffset)
    if (result.node) return result
    currentOffset = result.updatedOffset
  }

  return { node: null, offsetInNode: null, updatedOffset: currentOffset }
}

export const displayEntities = (userTaskID, parentID, transcription, entities, removeEntityFunction) => {
  if (!transcription) return

  for (const entity of entities) {
    // Create a fake range to display existing entities easily
    const range = document.createRange()

    const start = _findEntityEdgeNode(transcription, entity.offset, 0)
    range.setStart(start.node, start.offsetInNode)

    const end = _findEntityEdgeNode(transcription, entity.offset + entity.length, 1)
    range.setEnd(end.node, end.offsetInNode + 1)

    try {
      const tag = createTag(range, entity.entity_type)
      if (removeEntityFunction) addDeleteButton(userTaskID, parentID, entities, tag, entity, removeEntityFunction)
    } catch {
      /*
       * Remove any invalid entity to avoid display errors
       * This can happen if there are partially overlapping entities
       */
      entities.splice(entities.indexOf(entity), 1)
    }
  }
}
