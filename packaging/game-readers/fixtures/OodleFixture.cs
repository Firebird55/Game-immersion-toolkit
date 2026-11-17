// Authored span-ABI stand-in. This is not Oodle or any third-party/game code.
namespace OodleSharp;
public static class OodleDecompressor
{
    public static bool TryDecompress(ReadOnlySpan<byte> input, Span<byte> output, out int written)
    {
        written = 0;
        if (input.Length != output.Length + 1 || input[0] != 0x71) return false;
        for (int index = 0; index < output.Length; index++) output[index] = input[input.Length - index - 1];
        written = output.Length;
        return true;
    }
}
