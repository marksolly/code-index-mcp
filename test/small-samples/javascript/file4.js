class GetSetClass {
    constructor() {
        this._value = 0;
    }

    get dirty() {
        return this._value > 0;
    }

    set dirty(value) {
        this._value = value ? 1 : 0;
    }
}
