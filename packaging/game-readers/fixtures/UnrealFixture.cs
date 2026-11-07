// Authored stand-in for the reflected API. No upstream/game/decompression code.
public sealed class UnrealArchiveReader : IDisposable
{
    private readonly FixtureProvider _provider = null!;
    public UnrealArchiveReader(string install, string game, string unused)
    {
        // Production deliberately bypasses the supplier wrapper constructor.
        throw new InvalidOperationException("The authored wrapper must not be constructed.");
    }
    public void Dispose() { }
}
