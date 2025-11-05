"""Tests for visual differ tool.

This test suite verifies SSIM-based image comparison, pixel diff calculation,
and diff image generation.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("skimage.metrics")

from tests.visual.differ import DiffResult, VisualDiffer


@pytest.fixture
def solid_red_image():
    """Create 100x100 solid red image."""
    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    arr[:, :, 0] = 255  # Red channel
    return Image.fromarray(arr)


@pytest.fixture
def solid_blue_image():
    """Create 100x100 solid blue image."""
    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    arr[:, :, 2] = 255  # Blue channel
    return Image.fromarray(arr)


@pytest.fixture
def solid_white_image():
    """Create 100x100 solid white image."""
    arr = np.full((100, 100, 3), 255, dtype=np.uint8)
    return Image.fromarray(arr)


@pytest.fixture
def gradient_image():
    """Create 100x100 gradient image (left=black, right=white)."""
    arr = np.zeros((100, 100, 3), dtype=np.uint8)
    for x in range(100):
        arr[:, x, :] = int(x * 255 / 99)
    return Image.fromarray(arr)


class TestVisualDifferInit:
    """Test VisualDiffer initialization and validation."""
    
    def test_default_parameters(self):
        """Test default threshold and pixel_diff_threshold."""
        differ = VisualDiffer()
        assert differ.threshold == 0.95
        assert differ.pixel_diff_threshold == 10
    
    def test_custom_threshold(self):
        """Test custom SSIM threshold."""
        differ = VisualDiffer(threshold=0.98)
        assert differ.threshold == 0.98
    
    def test_custom_pixel_diff_threshold(self):
        """Test custom pixel difference threshold."""
        differ = VisualDiffer(pixel_diff_threshold=20)
        assert differ.pixel_diff_threshold == 20
    
    def test_invalid_threshold_too_low(self):
        """Test that threshold < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="threshold must be in"):
            VisualDiffer(threshold=-0.1)
    
    def test_invalid_threshold_too_high(self):
        """Test that threshold > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="threshold must be in"):
            VisualDiffer(threshold=1.1)
    
    def test_invalid_pixel_diff_threshold_negative(self):
        """Test that negative pixel_diff_threshold raises ValueError."""
        with pytest.raises(ValueError, match="pixel_diff_threshold must be in"):
            VisualDiffer(pixel_diff_threshold=-1)
    
    def test_invalid_pixel_diff_threshold_too_high(self):
        """Test that pixel_diff_threshold > 255 raises ValueError."""
        with pytest.raises(ValueError, match="pixel_diff_threshold must be in"):
            VisualDiffer(pixel_diff_threshold=256)
    
    def test_boundary_thresholds(self):
        """Test boundary values (0.0, 1.0, 0, 255) are valid."""
        # Should not raise
        VisualDiffer(threshold=0.0, pixel_diff_threshold=0)
        VisualDiffer(threshold=1.0, pixel_diff_threshold=255)


class TestSSIMComparison:
    """Test SSIM score calculation."""
    
    def test_identical_images(self, solid_red_image):
        """Test that identical images have SSIM = 1.0."""
        differ = VisualDiffer()
        result = differ.compare(solid_red_image, solid_red_image)
        assert result.ssim_score == pytest.approx(1.0)
        assert result.passed is True
    
    def test_completely_different_images(self, solid_red_image, solid_blue_image):
        """Test that completely different images have low SSIM."""
        differ = VisualDiffer(threshold=0.5)
        result = differ.compare(solid_red_image, solid_blue_image)
        # Red vs blue should be very different (SSIM close to 0)
        assert result.ssim_score < 0.5
        assert result.passed is False
    
    def test_minor_difference(self):
        """Test that images with minor differences have high SSIM."""
        # Create two nearly identical images
        base = np.full((100, 100, 3), 128, dtype=np.uint8)
        actual = base.copy()
        actual[50, 50] = [130, 130, 130]  # Change one pixel slightly
        
        differ = VisualDiffer(threshold=0.95)
        result = differ.compare(
            Image.fromarray(base),
            Image.fromarray(actual),
        )
        # One pixel difference should have very high SSIM
        assert result.ssim_score > 0.99
        assert result.passed is True
    
    def test_threshold_pass_fail(self, solid_white_image):
        """Test that threshold correctly determines pass/fail."""
        # Create images with noticeable difference
        base = np.full((100, 100, 3), 255, dtype=np.uint8)
        actual = base.copy()
        actual[0:50, 0:50] = [100, 100, 100]  # Darken quarter significantly

        # Should pass with low threshold
        differ_low = VisualDiffer(threshold=0.80)
        result_low = differ_low.compare(
            Image.fromarray(base),
            Image.fromarray(actual),
        )
        assert result_low.passed is True

        # Should fail with high threshold
        differ_high = VisualDiffer(threshold=0.99)
        result_high = differ_high.compare(
            Image.fromarray(base),
            Image.fromarray(actual),
        )
        assert result_high.passed is False


class TestPixelDiffPercentage:
    """Test pixel diff percentage calculation."""
    
    def test_identical_images_zero_diff(self, solid_red_image):
        """Test that identical images have 0% pixel diff."""
        differ = VisualDiffer()
        result = differ.compare(solid_red_image, solid_red_image)
        assert result.pixel_diff_percentage == 0.0
    
    def test_completely_different_100_percent(self, solid_red_image, solid_blue_image):
        """Test that completely different images have 100% diff."""
        differ = VisualDiffer(pixel_diff_threshold=10)
        result = differ.compare(solid_red_image, solid_blue_image)
        # Red vs blue: every pixel differs by 255 in channels
        assert result.pixel_diff_percentage == 100.0
    
    def test_partial_difference(self):
        """Test pixel diff percentage for partial changes."""
        # 100x100 image, change top half (5000 pixels)
        base = np.zeros((100, 100, 3), dtype=np.uint8)
        actual = base.copy()
        actual[0:50, :] = [255, 0, 0]  # Top half red
        
        differ = VisualDiffer(pixel_diff_threshold=10)
        result = differ.compare(
            Image.fromarray(base),
            Image.fromarray(actual),
        )
        # 50% of pixels changed
        assert result.pixel_diff_percentage == pytest.approx(50.0)
    
    def test_pixel_diff_threshold_filters_small_changes(self):
        """Test that pixel_diff_threshold filters out small changes."""
        # Create images with small differences (5 levels)
        base = np.full((100, 100, 3), 128, dtype=np.uint8)
        actual = base.copy()
        actual[:, :] = [133, 133, 133]  # +5 per channel
        
        # With threshold=10, should see no diff
        differ_high = VisualDiffer(pixel_diff_threshold=10)
        result_high = differ_high.compare(
            Image.fromarray(base),
            Image.fromarray(actual),
        )
        assert result_high.pixel_diff_percentage == 0.0
        
        # With threshold=3, should see 100% diff
        differ_low = VisualDiffer(pixel_diff_threshold=3)
        result_low = differ_low.compare(
            Image.fromarray(base),
            Image.fromarray(actual),
        )
        assert result_low.pixel_diff_percentage == 100.0


class TestDiffImageGeneration:
    """Test diff image generation."""
    
    def test_generate_diff_default_true(self, solid_red_image, solid_blue_image):
        """Test that diff image is generated by default."""
        differ = VisualDiffer()
        result = differ.compare(solid_red_image, solid_blue_image)
        assert result.diff_image is not None
        assert isinstance(result.diff_image, Image.Image)
    
    def test_generate_diff_false(self, solid_red_image, solid_blue_image):
        """Test that diff image is not generated when generate_diff=False."""
        differ = VisualDiffer()
        result = differ.compare(
            solid_red_image,
            solid_blue_image,
            generate_diff=False,
        )
        assert result.diff_image is None
    
    def test_diff_image_highlights_changes(self):
        """Test that diff image highlights changed regions in red."""
        # Create image with left half black, right half white
        base = np.zeros((100, 100, 3), dtype=np.uint8)
        base[:, 50:] = [255, 255, 255]  # Right half white
        
        # Change right half to blue
        actual = base.copy()
        actual[:, 50:] = [0, 0, 255]  # Right half blue
        
        differ = VisualDiffer()
        result = differ.compare(
            Image.fromarray(base),
            Image.fromarray(actual),
        )
        
        # Diff image should have red overlay on right half
        diff_arr = np.array(result.diff_image)
        
        # Left half (unchanged) should be black (or close to actual)
        assert np.all(diff_arr[:, 0, :] == [0, 0, 0])
        
        # Right half (changed) should be red
        assert np.all(diff_arr[:, 99, :] == [255, 0, 0])
    
    def test_diff_image_size_matches_input(self, solid_red_image, solid_blue_image):
        """Test that diff image has same size as input."""
        differ = VisualDiffer()
        result = differ.compare(solid_red_image, solid_blue_image)
        assert result.diff_image.size == solid_red_image.size


class TestDiffResult:
    """Test DiffResult dataclass."""
    
    def test_diff_result_fields(self, solid_red_image):
        """Test that all DiffResult fields are populated."""
        differ = VisualDiffer(threshold=0.95)
        result = differ.compare(solid_red_image, solid_red_image)
        
        assert isinstance(result, DiffResult)
        assert result.ssim_score == pytest.approx(1.0)
        assert result.pixel_diff_percentage == 0.0
        assert result.passed is True
        assert result.threshold == 0.95
        assert result.diff_image is not None
        assert result.baseline_shape == (100, 100, 3)
        assert result.actual_shape == (100, 100, 3)
    
    def test_save_diff_success(self, solid_red_image, solid_blue_image, tmp_path):
        """Test saving diff image to file."""
        differ = VisualDiffer()
        result = differ.compare(solid_red_image, solid_blue_image)
        
        output_path = tmp_path / "diff.png"
        result.save_diff(output_path)
        
        # Verify file was created
        assert output_path.exists()
        
        # Verify it's a valid image
        saved_img = Image.open(output_path)
        assert saved_img.size == solid_red_image.size
    
    def test_save_diff_no_diff_image_raises(self, solid_red_image, solid_blue_image, tmp_path):
        """Test that saving diff when no diff image raises ValueError."""
        differ = VisualDiffer()
        result = differ.compare(
            solid_red_image,
            solid_blue_image,
            generate_diff=False,
        )
        
        output_path = tmp_path / "diff.png"
        with pytest.raises(ValueError, match="No diff image available"):
            result.save_diff(output_path)


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_different_image_sizes_raises(self):
        """Test that comparing images of different sizes raises ValueError."""
        small = Image.new("RGB", (50, 50), color=(255, 0, 0))
        large = Image.new("RGB", (100, 100), color=(255, 0, 0))
        
        differ = VisualDiffer()
        with pytest.raises(ValueError, match="shapes don't match"):
            differ.compare(small, large)
    
    def test_grayscale_images_converted(self):
        """Test that grayscale images are converted to RGB."""
        gray1 = Image.new("L", (100, 100), color=128)
        gray2 = Image.new("L", (100, 100), color=128)
        
        differ = VisualDiffer()
        result = differ.compare(gray1, gray2)
        
        # Should succeed (converted to RGB)
        assert result.ssim_score == pytest.approx(1.0)
        assert result.passed is True
    
    def test_rgba_images_converted(self):
        """Test that RGBA images are converted to RGB."""
        rgba1 = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        rgba2 = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        
        differ = VisualDiffer()
        result = differ.compare(rgba1, rgba2)
        
        # Should succeed (alpha channel ignored after conversion)
        assert result.ssim_score == pytest.approx(1.0)
        assert result.passed is True
    
    def test_small_1x1_image(self):
        """Test that 1x1 images work correctly."""
        img1 = Image.new("RGB", (1, 1), color=(255, 0, 0))
        img2 = Image.new("RGB", (1, 1), color=(255, 0, 0))
        
        differ = VisualDiffer()
        result = differ.compare(img1, img2)
        
        assert result.ssim_score == pytest.approx(1.0)
        assert result.passed is True
    
    def test_large_image_1000x1000(self):
        """Test that large images work correctly."""
        # Create 1000x1000 solid color images
        arr1 = np.full((1000, 1000, 3), 128, dtype=np.uint8)
        arr2 = arr1.copy()
        
        differ = VisualDiffer()
        result = differ.compare(
            Image.fromarray(arr1),
            Image.fromarray(arr2),
        )
        
        assert result.ssim_score == pytest.approx(1.0)
        assert result.passed is True


class TestIntegration:
    """Integration tests with realistic scenarios."""
    
    def test_gradient_vs_solid(self, gradient_image, solid_white_image):
        """Test comparing gradient to solid color."""
        differ = VisualDiffer(threshold=0.8)
        result = differ.compare(gradient_image, solid_white_image)
        
        # Should be quite different
        assert result.ssim_score < 0.9
        assert result.pixel_diff_percentage > 0.0
    
    def test_workflow_with_failure_detection(self, tmp_path):
        """Test full workflow: compare, detect failure, save diff."""
        # Create baseline and actual with differences
        baseline = np.full((100, 100, 3), 200, dtype=np.uint8)
        actual = baseline.copy()
        actual[25:75, 25:75] = [100, 100, 100]  # Darken center
        
        differ = VisualDiffer(threshold=0.95)
        result = differ.compare(
            Image.fromarray(baseline),
            Image.fromarray(actual),
        )
        
        # Should fail due to large change
        assert not result.passed
        
        # Save diff for debugging
        diff_path = tmp_path / "failure_diff.png"
        result.save_diff(diff_path)
        
        # Verify diff was saved
        assert diff_path.exists()
        
        # Verify diff has red overlay in center
        diff_img = Image.open(diff_path)
        diff_arr = np.array(diff_img)
        center_pixel = diff_arr[50, 50]
        assert tuple(center_pixel) == (255, 0, 0)  # Red
