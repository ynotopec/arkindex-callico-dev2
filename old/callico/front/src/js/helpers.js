import { TRANSLATIONS, IMAGE_WARNING_RATIO, POLYGON_MIN_SIZE, POLYGON_MAX_POINTS } from './config.js'
import { cloneDeep, isEqual } from 'lodash'

export const pluralize = (label, count) => {
  return count + ' ' + label + (count > 1 ? 's' : '')
}

/**
 * Compute the width of the screen multiplied by the ratio
 *
 * @param {number} ratio Ratio
 * @returns {number} Width of the screen multiplied by the ratio
 */
export const iiifWidth = (ratio) => {
  return Math.ceil(window.innerWidth * ratio / 100) * 100
}

/**
 * Generate a IIIF URI for a JPEG image with the default profile and no rotation,
 * optionally cropping to a element's polygon and optionally limiting to a maximum size.
 *
 * @param {{image: {width: number, height: number, url: string}, polygon?: [number, number][]}} element Element to get a IIIF URI for.
 * @param {{width?: number, height?: number}} param1
 *   Optional maximum width and height of the resulting image.
 * @returns {string} An IIIF URI.
 */
export const iiifUri = (element, { width, height } = {}) => {
  if (!element.image) throw new Error('An image is required.')
  if ((element.image.width ?? 0) <= 0 || (element.image.height ?? 0) <= 0) throw new Error('An image with valid dimensions is required.')
  if (!element.image.url) throw new Error('An image with a valid URL is required.')

  if (!width) width = null
  if (!height) height = null

  let url = element.image.url
  if (!url.endsWith('/')) url += '/'

  // By default, use the entire image as a bounding box
  let box = { x: 0, y: 0, width: element.image.width, height: element.image.height }

  // Do not crop if there is no polygon
  if (!element.polygon) url += 'full'
  else {
    box = boundingBox(element)
    /*
     * Do not crop if the box just fits the entire image.
     * Some IIIF servers are not clever enough to guess this on their own and optimize
     */
    if (box.x <= 0 && box.y <= 0 && box.width >= element.image.width && box.height >= element.image.height) url += 'full'
    else url += [box.x, box.y, box.width, box.height].join(',')
  }

  // Only one dimension is greater than the image; resize both resize parameters before applying it to avoid going over 100% of the image
  if (width > box.width ^ height > box.height) {
    const ratio = Math.max(width / box.width, height / box.height)
    if (width) width = Math.round(width / ratio)
    if (height) height = Math.round(height / ratio)
  }

  // When both the specified maximum width and height are greater than or equal to the image's size, just use full
  if ((width ?? Infinity) >= box.width && (height ?? Infinity) >= box.height) return url + '/full/0/default.jpg'

  // Add a ! prefix to require the IIIF server to preserve aspect ratio if we set both dimensions at once in a resize
  return `${url}/${(width && height) ? '!' : ''}${width ?? ''},${height ?? ''}/0/default.jpg`
}

/**
 * The image check found an invalid size.
 */
export class InvalidImageSizeError extends Error {
  constructor (...args) {
    super(...args)
    // Not setting this would make the error look like a normal Error
    this.name = this.constructor.name
  }
}

/**
 * Check that the image size is as expected, to detect IIIF server issues
 */
export const checkImageSize = (img, expectedWidth, expectedHeight, imageURL) => {
  const ratios = [
    img.width / expectedWidth,
    img.height / expectedHeight,
    (img.width * img.height) / (expectedWidth * expectedHeight)
  ]
  if (ratios.some(ratio => ratio < IMAGE_WARNING_RATIO || ratio > (-IMAGE_WARNING_RATIO + 2))) {
    throw new InvalidImageSizeError(TRANSLATIONS.imageSizeError(`${img.width}×${img.height}`, `${expectedWidth}×${expectedHeight}`, imageURL))
  }
}

/**
 * Check for point equality.
 *
 * @param {[number, number]} param0 First point to compare.
 * @param {[number, number]} param1 Second point to compare.
 * @returns {boolean} Whether both points are equal.
 */
export const pointsEqual = ([x1, y1], [x2, y2]) => { return x1 === x2 && y1 === y2 }

/**
 * Shifts a polygon depending on a 2-dimensional vector
 *
 * @param {[number, number][]} polygon Polygon.
 * @param {[number, number]} vector Shifting vector.
 * @returns {[number, number][]} Shifted polygon.
 */
export const shiftPolygon = (points, [offsetX, offsetY]) => {
  return points.map(([x, y]) => [x + offsetX, y + offsetY])
}

/**
 * Convert a polygon coordinates to SVG syntax
 *
 * @param {[number, number][]} polygon Polygon
 * @returns {string} SVG Coordinates
 */
export const svgPolygon = polygon => {
  return polygon
    .map(point => point.join(','))
    .join(' ')
}

/**
 * Return width and height of a polygon
 * @param {[number, number][]} polygon Polygon.
 * @returns {[number, number]} Width and height of the polygon.
 */
export const getSize = (polygon) => {
  const xCoords = polygon.map(p => p[0])
  const yCoords = polygon.map(p => p[1])
  const x = Math.min(...xCoords)
  const y = Math.min(...yCoords)
  const width = Math.max(...xCoords) - x
  const height = Math.max(...yCoords) - y
  return [width, height]
}

/**
 * Determine if two polygon geometrically represent the same area.
 * @param {[number, number][]} polygon1 First polygon to compare.
 * @param {[number, number][]} polygon2 Second polygon to compare.
 * @returns {boolean} Whether or not the two polygons are geometrically equal.
 */
export const polygonsEqual = (polygon1, polygon2) => isEqual(checkPolygon(polygon1), checkPolygon(polygon2))

/**
 * Generate a rectangle bounding box for an element, optionally without exceeding the image's dimensions.
 * @param {{polygon: [number, number][], image?: {width: number, height: number}}} element
 *   Element as returned by an ElementSerializer. The `image` is optional only if `imageBounds` is false.
 * @param {{margin?: number, imageBounds?: boolean}} options
 *   Allow the bounding box to exceed the image's dimensions.
 * @returns {{x: number, y: number, width: number, height: number}} A rectangular bounding box.
 */
export const boundingBox = (element, { imageBounds = true } = {}) => {
  // Create externally-squared iiif coords from element polygon
  const xCoords = element.polygon ? element.polygon.map(e => e[0]) : [0, element.image.width]
  const yCoords = element.polygon ? element.polygon.map(e => e[1]) : [0, element.image.height]
  let minX = Math.min(...xCoords)
  let minY = Math.min(...yCoords)
  let maxX = Math.max(...xCoords)
  let maxY = Math.max(...yCoords)

  if (imageBounds) {
    // Require an image to ensure we can properly restrict the bounding box to the image
    if (!element.image) throw new Error('An image is required.')
    if ((element.image.width ?? 0) <= 0 || (element.image.height ?? 0) <= 0) throw new Error('An image with valid dimensions is required.')

    // Restrict to the image's dimensions
    minX = Math.min(element.image.width, Math.max(minX, 0))
    minY = Math.min(element.image.height, Math.max(minY, 0))
    maxX = Math.min(element.image.width, Math.max(maxX, 0))
    maxY = Math.min(element.image.height, Math.max(maxY, 0))
  }

  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY
  }
}

/**
 * Convert an angle from degrees to radians.
 * @param {number} degrees Angle in degrees.
 * @returns {number} Angle in radians.
 */
export const toRadians = degrees => degrees * Math.PI / 180

/**
 * Rotate a point clockwise around an origin point by an angle.
 * @param {[number, number]} point Point to rotate.
 * @param {[number, number]} origin Origin point to rotate around.
 * @param {number} angle Angle in degrees.
 * @returns {[number, number]} Coordinates of the rotated point.
 */
export const rotateAround = (point, origin = [0, 0], angle = 0) => {
  if (!angle) return point
  const radians = toRadians(angle)
  const [originX, originY] = origin
  const [x, y] = point
  const [relativeX, relativeY] = [x - originX, y - originY]
  return [
    (relativeX * Math.cos(radians) - relativeY * Math.sin(radians)) + originX,
    (relativeY * Math.cos(radians) + relativeX * Math.sin(radians)) + originY
  ]
}

/**
 * The polygon reordering found the polygon to be invalid.
 */
export class InvalidPolygonError extends Error {
  constructor (...args) {
    super(...args)
    // Not setting this would make the error look like a normal Error
    this.name = this.constructor.name
  }
}

/**
 * Quick sanity checks for some constraints on polygons:
 *
 * - Remove duplicate points (ABBC → ABC)
 * - Check the polygon has at least 3 distinct points and at most 165 distinct points
 * - Check that the polygon is not too small
 *
 * Some backend constraints are not fully tested:
 *
 * - It is assumed that the backend will automatically close open polygons
 * - Self-intersection is not tested (e.g. bowtie polygons)
 *
 * @param {[number, number][]} polygon Polygon to reorder.
 * @param {number} minSize Minimum allowed width/height.
 * @returns {[number, number][]} A sanitized polygon.
 * @throws {InvalidPolygonError} When the polygon will be considered invalid by the backend.
 */
export const checkPolygon = (polygon, minSize = POLYGON_MIN_SIZE) => {
  if (!Array.isArray(polygon)) throw new TypeError(`Expected Array, got ${polygon}`)
  for (const index in polygon) {
    const point = polygon[index]
    if (!Array.isArray(point) || point.length !== 2 || !Number.isFinite(point[0]) || !Number.isFinite(point[1])) {
      throw new TypeError(`Point ${index}: expected Array of two finite numbers, got ${point}`)
    }
  }

  const newPolygon = cloneDeep(polygon)

  // Round a polygon's points coords to integers
  newPolygon.forEach((point, index) => {
    newPolygon[index] = point.map(Math.round)
  })

  // Ensure all coordinates are positive
  if (newPolygon.find(point => point.find(coord => coord < 0))) {
    throw new InvalidPolygonError('A polygon cannot have negative coordinates.')
  }

  // Deduplicate polygon: ABBCCBCA → ABCBCA
  let j = 1
  while (j < newPolygon.length) {
    if (pointsEqual(newPolygon[j], newPolygon[j - 1])) {
      newPolygon.splice(j, 1)
    } else {
      j++
    }
  }

  /*
   * Require three *unique* points: we already made a deduplication, so we could only check the length,
   * but if the first and last points are equal, we will need a length of 4.
   */
  if (newPolygon.length < (3 + pointsEqual(newPolygon[0], newPolygon[newPolygon.length - 1]))) {
    throw new InvalidPolygonError('This polygon does not have at least three unique points.')
  }

  /*
   * Polygons should have at most 163 distinct points.
   * 164 points are allowed only if the first and last point are equal
   */
  if (newPolygon.length > POLYGON_MAX_POINTS + 1 || (
    newPolygon.length === POLYGON_MAX_POINTS + 1 &&
    !pointsEqual(newPolygon[0], newPolygon[POLYGON_MAX_POINTS])
  )) {
    throw new InvalidPolygonError(`This polygon has more than ${POLYGON_MAX_POINTS} distinct points.`)
  }

  /*
   * Assert polygon width and height are sufficient
   * The correct way to handle this would be to calculate the polygon area
   */
  const [width, height] = getSize(newPolygon)
  if (height < minSize || width < minSize) throw new InvalidPolygonError('This polygon is too small.')

  return newPolygon
}
