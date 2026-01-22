#!/bin/bash
# Convenience script to run corpus tests on W3C SVG test suite files
#
# Usage:
#   ./tests/corpus/run_w3c_corpus.sh                 # Run all categories
#   ./tests/corpus/run_w3c_corpus.sh gradients       # Run gradients only
#   ./tests/corpus/run_w3c_corpus.sh shapes --mode legacy  # Run shapes in legacy mode

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
CATEGORY="${1:-all}"
shift || true

echo -e "${BLUE}SVG2OOXML W3C Corpus Testing${NC}"
echo "Category: $CATEGORY"
echo ""

# Function to run corpus for a category
run_category() {
    local category=$1
    local category_name=$2
    local limit=${3:-50}

    echo -e "${YELLOW}Generating metadata for $category_name...${NC}"
    python "$SCRIPT_DIR/add_w3c_corpus.py" \
        --category "$category" \
        --limit "$limit" \
        --output "$SCRIPT_DIR/w3c/w3c_${category_name}_metadata.json"

    echo -e "${YELLOW}Running corpus tests for $category_name...${NC}"
    # Extract only the extra arguments passed to the script (like --mode)
    # by shifting the 3 internal positional parameters of this function
    local extra_args=("${@:4}")
    
    python "$SCRIPT_DIR/run_corpus.py" \
        --corpus-dir "$PROJECT_ROOT/tests/svg" \
        --output-dir "$SCRIPT_DIR/w3c/output_${category_name}" \
        --report "$SCRIPT_DIR/w3c/report_${category_name}.json" \
        --metadata "$SCRIPT_DIR/w3c/w3c_${category_name}_metadata.json" \
        "${extra_args[@]}"

    echo -e "${GREEN}✓ Completed $category_name${NC}"
    echo ""
}

# Run tests based on category
case "$CATEGORY" in
    gradients)
        run_category "pservers-grad" "gradients" 25 "$@"
        ;;
    shapes)
        run_category "shapes" "shapes" 30 "$@"
        ;;
    paths)
        run_category "paths-data" "paths" 25 "$@"
        ;;
    text)
        run_category "text" "text" 20 "$@"
        ;;
    masking)
        run_category "masking" "masking" 20 "$@"
        ;;
    painting)
        run_category "painting" "painting" 25 "$@"
        ;;
    filters)
        run_category "filters" "filters" 15 "$@"
        ;;
    all)
        echo -e "${BLUE}Running all test categories...${NC}"
        echo ""

        run_category "pservers-grad" "gradients" 25 "$@"
        run_category "shapes" "shapes" 30 "$@"
        run_category "paths-data" "paths" 25 "$@"
        run_category "text" "text" 20 "$@"
        run_category "masking" "masking" 20 "$@"
        run_category "painting" "painting" 25 "$@"

        echo -e "${GREEN}✓ All categories completed${NC}"
        echo ""
        echo "Summary reports:"
        ls -1 "$SCRIPT_DIR/w3c/report_"*.json
        ;;
    *)
        echo "Unknown category: $CATEGORY"
        echo ""
        echo "Usage: $0 [category] [options]"
        echo ""
        echo "Categories:"
        echo "  gradients  - Linear and radial gradient tests"
        echo "  shapes     - Basic shape tests (rect, circle, ellipse, etc.)"
        echo "  paths      - Path data tests"
        echo "  text       - Text rendering tests"
        echo "  masking    - Mask and clip-path tests"
        echo "  painting   - Fill, stroke, marker tests"
        echo "  filters    - Filter effects tests"
        echo "  all        - Run all categories"
        echo ""
        echo "Options:"
        echo "  --mode legacy|resvg   - Rendering mode (default: resvg)"
        exit 1
        ;;
esac
