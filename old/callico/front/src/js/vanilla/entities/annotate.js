import { isEmpty, isEqual, xorWith } from 'lodash'
import { initFormset } from '../utils/formset.js'
import { SELECTED_LABEL, initLabels } from './labels.js'
import { loadStoredEntities } from './storage.js'
import { createTag, addDeleteButton, displayEntities } from './base.js'
import { setUserTaskAnnotation, displayWarning } from '../annotations/storage.js'

const TRANSCRIPTION_TEXT_ID = 'transcription-text'

// List of characters not considered as being part of a word for full word selection
const FULL_WORDS_DELIMITERS = [' ', '\n']

const enforceFullWordSelection = (selection) => {
  /**
   * Shrinks or expands the range of a selection to round it to
   * characters that are not present in FULL_WORDS_DELIMITERS.
   */
  const currentRange = selection.getRangeAt(0)
  if (currentRange.startOffset === currentRange.endOffset) return currentRange

  let startIndex = currentRange.startOffset
  const startText = currentRange.startContainer.textContent

  // Determine the start index of the new selection
  if (FULL_WORDS_DELIMITERS.includes(startText[startIndex])) {
    // If the start index is not within a word, shrink the selection forwards until we reach a word
    while (FULL_WORDS_DELIMITERS.includes(startText[startIndex])) startIndex++
  } else {
    // Else expand the selection backwards until we reach the last character being part of a word
    while (startIndex > 0 && !FULL_WORDS_DELIMITERS.includes(startText[startIndex - 1])) startIndex--
  }

  // The index of the last character of a selection, i.e. offset - 1
  let endIndex = currentRange.endOffset - 1
  const endText = currentRange.endContainer.textContent

  // Determine the end index of the new selection
  if (FULL_WORDS_DELIMITERS.includes(endText[endIndex])) {
    // If the end index is not within a word, shrink the selection backwards until we reach a word
    while (FULL_WORDS_DELIMITERS.includes(endText[endIndex])) endIndex--
  } else {
    // Else expand the selection forwards until we reach the last character being part of a word
    while (endIndex < (endText.length - 1) && !FULL_WORDS_DELIMITERS.includes(endText[endIndex + 1])) endIndex++
  }

  const newRange = document.createRange()
  newRange.setStart(currentRange.startContainer, startIndex)
  // Restore the range end offset, i.e. index + 1
  newRange.setEnd(currentRange.endContainer, endIndex + 1)
  selection.removeAllRanges()
  selection.addRange(newRange)
  return newRange
}

const _retrieveFlatOffset = (node, stopNode, currentOffset) => {
  if (node === stopNode) return { stop: true, flatOffset: currentOffset }

  if (node.nodeName === '#text') currentOffset += node.textContent.length

  for (const child of node.childNodes) {
    const result = _retrieveFlatOffset(child, stopNode, currentOffset)
    if (result.stop) return result

    currentOffset = result.flatOffset
  }

  return { stop: false, flatOffset: currentOffset }
}

const _addEntity = (userTaskID, parentID, entities, fullWordSelection) => {
  const selection = document.getSelection()

  if (selection.rangeCount === 0) return
  let range = selection.getRangeAt(selection.rangeCount - 1)
  if (selection.rangeCount > 1) {
    /**
     * Firefox can handle 2+ ranges under specific conditions (e.g. enclosing existing entities).
     * In this case, we mimic Chromium's behavior by updating the start container and offset to
     * the values from the range at the first index.
     */
    const newRange = document.createRange()
    newRange.setStart(selection.getRangeAt(0).startContainer, selection.getRangeAt(0).startOffset)
    newRange.setEnd(range.endContainer, range.endOffset)
    selection.removeAllRanges()
    selection.addRange(newRange)
    range = newRange
  }

  // Check that the selection is part of the transcription
  const transcription = document.getElementById(TRANSCRIPTION_TEXT_ID)
  if (!transcription.contains(range.startContainer) || !transcription.contains(range.endContainer) || range.startContainer.nodeName !== '#text') return

  if (fullWordSelection) range = enforceFullWordSelection(selection)

  const entityText = range.toString()
  if (!entityText || !SELECTED_LABEL) return

  const flatOffset = _retrieveFlatOffset(transcription, range.startContainer, 0).flatOffset
  const entity = {
    entity_type: SELECTED_LABEL,
    offset: flatOffset + range.startOffset,
    length: entityText.length
  }
  // Prevent from annotating the same entity twice at the same position
  if (entities.some(existing => (
    existing.entity_type === entity.entity_type &&
    existing.offset === entity.offset &&
    existing.length === entity.length
  ))) return

  try {
    const tag = createTag(range, entity.entity_type)
    addDeleteButton(userTaskID, parentID, entities, tag, entity, _removeEntity)

    // If we are able to create a surrounding HTML tag, it means the entity is valid and can be saved
    entities.push(entity)
    setUserTaskAnnotation(userTaskID, parentID, entities)

    selection.removeAllRanges()
  } catch {
    // Otherwise, the selection probably partially overlaps one or two entities, we skip it
  }
}

const _removeEntity = (entities, tag, entity) => {
  entities.splice(entities.indexOf(entity), 1)

  const parent = tag.parentNode

  const filteredChildren = []
  for (const child of tag.childNodes) {
    if (child.nodeName === 'BUTTON') continue
    filteredChildren.push(child)
  }
  tag.replaceWith(...filteredChildren)

  // Merge adjacent text nodes to avoid selection bugs
  parent.normalize()
}

const initEntities = (userTaskID, parentID, transcription, entities, fullWordSelection) => {
  // Display entities of the previous version
  displayEntities(userTaskID, parentID, transcription, entities, _removeEntity)

  transcription.addEventListener('mouseup', () => {
    _addEntity(userTaskID, parentID, entities, fullWordSelection)
  })
}

export const bootEntitiesTranscriptionAnnotate = (userTaskID, parentID, previousEntities, fullWordSelection) => {
  const transcription = document.getElementById(TRANSCRIPTION_TEXT_ID)

  const entities = loadStoredEntities(userTaskID, parentID, transcription) || previousEntities
  if (!isEmpty(xorWith(entities, previousEntities, isEqual))) displayWarning(userTaskID, parentID)

  initEntities(userTaskID, parentID, transcription, entities, fullWordSelection)
  initLabels()
  initFormset(entities, (key, value) => value)
}
